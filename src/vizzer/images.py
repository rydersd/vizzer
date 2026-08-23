"""Small, dependency-free validators for image evidence.

The validators inspect the complete byte structure; filename extensions and
caller-provided media types are never trusted.  This module deliberately has no
review-workflow knowledge so other optional features can use it.
"""
from __future__ import annotations

import binascii
import struct
import zlib


_MAX_DECODED_BYTES = 128 * 1024 * 1024


def _png_row_sizes(width: int, height: int, bits_per_pixel: int,
                   interlace: int) -> list[int]:
    if interlace == 0:
        return [(width * bits_per_pixel + 7) // 8] * height
    passes = (
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
        (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2),
    )
    rows: list[int] = []
    for start_x, start_y, step_x, step_y in passes:
        pass_width = max(0, (width - start_x + step_x - 1) // step_x)
        pass_height = max(0, (height - start_y + step_y - 1) // step_y)
        if pass_width:
            rows.extend([(pass_width * bits_per_pixel + 7) // 8] * pass_height)
    return rows


def _is_png(data: bytes) -> bool:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset = 8
    ihdr = None
    compressed = bytearray()
    saw_idat = False
    idat_closed = False
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        chunk_type = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data) or not all(
                65 <= value <= 90 or 97 <= value <= 122 for value in chunk_type):
            return False
        payload = data[offset + 8:offset + 8 + length]
        expected_crc = int.from_bytes(data[offset + 8 + length:end], "big")
        if (binascii.crc32(chunk_type + payload) & 0xffffffff) != expected_crc:
            return False
        if offset == 8 and chunk_type != b"IHDR":
            return False
        if chunk_type == b"IHDR":
            if ihdr is not None or length != 13:
                return False
            ihdr = payload
        elif chunk_type == b"IDAT":
            if ihdr is None or idat_closed:
                return False
            saw_idat = True
            compressed.extend(payload)
        elif saw_idat:
            idat_closed = True
        offset = end
        if chunk_type == b"IEND":
            if length != 0 or offset != len(data):
                return False
            break
    else:
        return False
    if ihdr is None or not saw_idat:
        return False
    width, height, depth, colour, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", ihdr)
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    legal_depths = {
        0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8},
        4: {8, 16}, 6: {8, 16},
    }
    if (not width or not height or width > 65535 or height > 65535
            or channels is None or depth not in legal_depths[colour]
            or compression != 0 or filtering != 0 or interlace not in {0, 1}):
        return False
    expected_size = sum(
        size + 1 for size in _png_row_sizes(
            width, height, channels * depth, interlace
        )
    )
    if expected_size > _MAX_DECODED_BYTES:
        return False
    try:
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(bytes(compressed), expected_size + 1)
    except zlib.error:
        return False
    if (len(decoded) != expected_size or not inflater.eof
            or inflater.unconsumed_tail or inflater.unused_data):
        return False
    cursor = 0
    for row_size in _png_row_sizes(width, height, channels * depth, interlace):
        if decoded[cursor] > 4:
            return False
        cursor += row_size + 1
    return cursor == len(decoded)


_JPEG_SOF = {
    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
}


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10 or data[:2] != b"\xff\xd8":
        return None
    offset = 2
    dimensions = None
    saw_scan = False
    while offset < len(data):
        if data[offset] != 0xFF:
            return None
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            return None
        marker = data[offset]
        offset += 1
        if marker == 0xD9:
            return dimensions if dimensions and saw_scan and offset == len(data) else None
        if marker in {0x01, *range(0xD0, 0xD8)}:
            continue
        if marker in {0x00, 0xD8} or offset + 2 > len(data):
            return None
        length = int.from_bytes(data[offset:offset + 2], "big")
        if length < 2 or offset + length > len(data):
            return None
        segment = data[offset + 2:offset + length]
        offset += length
        if marker in _JPEG_SOF:
            if len(segment) < 6:
                return None
            height = int.from_bytes(segment[1:3], "big")
            width = int.from_bytes(segment[3:5], "big")
            components = segment[5]
            if not width or not height or not components or len(segment) != 6 + 3 * components:
                return None
            dimensions = (width, height)
        if marker != 0xDA:
            continue
        if dimensions is None or len(segment) < 6:
            return None
        components = segment[0]
        if not components or len(segment) != 4 + 2 * components:
            return None
        saw_scan = True
        while offset < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker_offset = offset
            while marker_offset < len(data) and data[marker_offset] == 0xFF:
                marker_offset += 1
            if marker_offset >= len(data):
                return None
            scan_marker = data[marker_offset]
            if scan_marker == 0x00 or 0xD0 <= scan_marker <= 0xD7:
                offset = marker_offset + 1
                continue
            offset = marker_offset - 1
            break
    return None


def _valid_vp8(payload: bytes) -> bool:
    return bool(
        len(payload) >= 10 and not payload[0] & 1
        and payload[3:6] == b"\x9d\x01\x2a"
        and int.from_bytes(payload[6:8], "little") & 0x3FFF
        and int.from_bytes(payload[8:10], "little") & 0x3FFF
    )


def _valid_vp8l(payload: bytes) -> bool:
    return bool(
        len(payload) >= 5 and payload[0] == 0x2F
        and not int.from_bytes(payload[1:5], "little") >> 29
    )


def _webp_chunks(data: bytes) -> bool:
    offset = 0
    saw_image = False
    while offset + 8 <= len(data):
        fourcc = data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        start = offset + 8
        end = start + size
        padded_end = end + (size & 1)
        if end > len(data) or padded_end > len(data):
            return False
        payload = data[start:end]
        if fourcc == b"VP8 ":
            if not _valid_vp8(payload):
                return False
            saw_image = True
        elif fourcc == b"VP8L":
            if not _valid_vp8l(payload):
                return False
            saw_image = True
        elif fourcc == b"VP8X":
            if len(payload) != 10 or payload[0] & 0xC1 or payload[1:4] != b"\0\0\0":
                return False
        elif fourcc == b"ANMF":
            if len(payload) < 24 or not _webp_chunks(payload[16:]):
                return False
            saw_image = True
        offset = padded_end
    return offset == len(data) and saw_image


def _is_webp(data: bytes) -> bool:
    return bool(
        len(data) >= 20 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        and int.from_bytes(data[4:8], "little") == len(data) - 8
        and _webp_chunks(data[12:])
    )


def image_media_type(data: bytes) -> str | None:
    """Return a media type only when the complete byte structure validates."""
    if _is_png(data):
        return "image/png"
    if _jpeg_dimensions(data) is not None:
        return "image/jpeg"
    if _is_webp(data):
        return "image/webp"
    return None


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Return validated image dimensions without external image tooling."""
    media_type = image_media_type(data)
    if media_type == "image/png":
        return struct.unpack(">II", data[16:24])
    if media_type == "image/jpeg":
        return _jpeg_dimensions(data)
    if media_type == "image/webp":
        chunks = data[12:]
        offset = 0
        while offset + 8 <= len(chunks):
            fourcc = chunks[offset:offset + 4]
            size = int.from_bytes(chunks[offset + 4:offset + 8], "little")
            payload = chunks[offset + 8:offset + 8 + size]
            if fourcc == b"VP8 ":
                return (
                    int.from_bytes(payload[6:8], "little") & 0x3FFF,
                    int.from_bytes(payload[8:10], "little") & 0x3FFF,
                )
            if fourcc == b"VP8L":
                packed = int.from_bytes(payload[1:5], "little")
                return ((packed & 0x3FFF) + 1, ((packed >> 14) & 0x3FFF) + 1)
            if fourcc == b"VP8X":
                return (
                    int.from_bytes(payload[4:7], "little") + 1,
                    int.from_bytes(payload[7:10], "little") + 1,
                )
            offset += 8 + size + (size & 1)
    return None
