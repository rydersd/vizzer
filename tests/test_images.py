import base64

from vizzer.images import image_dimensions, image_media_type


PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAA"
    "AABJRU5ErkJggg=="
)


def test_valid_png_reports_media_type_and_dimensions():
    assert image_media_type(PNG_1PX) == "image/png"
    assert image_dimensions(PNG_1PX) == (1, 1)


def test_extension_like_prefix_is_not_accepted_as_an_image():
    assert image_media_type(b"\x89PNG\r\n\x1a\nnot-a-png") is None
    assert image_dimensions(b"\x89PNG\r\n\x1a\nnot-a-png") is None


def test_trailing_bytes_invalidate_an_otherwise_valid_png():
    assert image_media_type(PNG_1PX + b"secret") is None
