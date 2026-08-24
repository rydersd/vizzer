"""Renderer-neutral object detail shared by Vizzer perspectives.

Adapters own source parsing.  Renderers receive this normalized payload and do
not infer repository layout, Markdown headings, language, or framework.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .model import Item


SCHEMA = "vizzer-object-detail/v1"
MAX_DETAIL_BYTES = 64 * 1024
SECTION_NAMES = ("reviewSteps", "acceptance", "definitionOfDone")


class ObjectDetailError(ValueError):
    """Raised when an adapter supplies an unsafe or malformed detail payload."""


def _bounded_text(value: object, subject: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ObjectDetailError(f"{subject} must be a string")
    if len(value) > maximum:
        raise ObjectDetailError(f"{subject} exceeds {maximum} characters")
    return value


def object_detail_for(item: Item, *, sections: dict[str, object] | None = None) -> dict[str, Any]:
    """Build the portable floor from normalized graph truth.

    ``sections`` is deliberately injected.  A spec-tree, API, database, or
    review-plan adapter may derive richer owner-facing sections without making
    this core contract recognize one source format.
    """
    supplied = sections or {}
    detail = {
        "schema": SCHEMA,
        "id": item.id,
        "title": item.title,
        "summary": item.one_liner or "",
        "status": item.status,
        "sections": {
            name: copy.deepcopy(supplied.get(name))
            for name in SECTION_NAMES
            if supplied.get(name) is not None
        },
        "core": {
            "role": item.role,
            "release": item.release or "",
            "appetite": item.appetite or "",
            "tags": list(item.tags),
            "flags": list(item.flags),
            "facets": copy.deepcopy(item.facets),
        },
        "relationships": {
            "dependsOn": list(item.deps),
            "typed": [
                {"kind": relation.kind, "target": relation.target}
                for relation in item.relations
            ],
        },
        "provenance": {
            "adapter": item.source.get("adapter", ""),
            "locator": item.source.get("path", ""),
        },
    }
    validate_object_detail(detail)
    return detail


def object_detail_identity(
    item: Item, *, sections: dict[str, object] | None = None,
) -> str:
    """Fingerprint every semantic input without retaining a dossier dictionary."""
    supplied = sections or {}
    payload = [
        SCHEMA,
        item.id,
        item.title,
        item.one_liner or "",
        item.status,
        [
            [name, supplied[name]]
            for name in SECTION_NAMES
            if supplied.get(name) is not None
        ],
        item.role,
        item.release or "",
        item.appetite or "",
        item.tags,
        item.flags,
        item.facets,
        item.deps,
        [[relation.kind, relation.target] for relation in item.relations],
        item.source.get("adapter", ""),
        item.source.get("path", ""),
    ]
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_object_detail(value: object) -> None:
    """Validate bounded JSON data without assigning source-format semantics."""
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ObjectDetailError(f"object detail schema must be {SCHEMA}")
    for field, maximum in (("id", 500), ("title", 500), ("summary", 4_000),
                           ("status", 120)):
        _bounded_text(value.get(field), f"object detail {field}", maximum)

    sections = value.get("sections")
    if not isinstance(sections, dict) or set(sections) - set(SECTION_NAMES):
        raise ObjectDetailError("object detail sections contain unknown names")
    for name, section in sections.items():
        if not isinstance(section, (str, list, dict)):
            raise ObjectDetailError(f"object detail section {name} must be JSON content")

    core = value.get("core")
    if not isinstance(core, dict):
        raise ObjectDetailError("object detail core must be an object")
    for field in ("role", "release", "appetite"):
        _bounded_text(core.get(field), f"object detail core {field}", 500)
    for field in ("tags", "flags"):
        entries = core.get(field)
        if not isinstance(entries, list) or len(entries) > 64:
            raise ObjectDetailError(f"object detail core {field} must be a bounded list")
        for entry in entries:
            _bounded_text(entry, f"object detail core {field} entry", 500)
    facets = core.get("facets")
    if not isinstance(facets, dict) or len(facets) > 64:
        raise ObjectDetailError("object detail facets must be a bounded object")
    for name, entries in facets.items():
        _bounded_text(name, "object detail facet name", 120)
        if not isinstance(entries, list) or len(entries) > 64:
            raise ObjectDetailError("object detail facet values must be bounded lists")
        for entry in entries:
            _bounded_text(entry, "object detail facet value", 500)

    relationships = value.get("relationships")
    if not isinstance(relationships, dict):
        raise ObjectDetailError("object detail relationships must be an object")
    dependencies = relationships.get("dependsOn")
    typed = relationships.get("typed")
    if not isinstance(dependencies, list) or len(dependencies) > 2_000:
        raise ObjectDetailError("object detail dependencies must be a bounded list")
    for entry in dependencies:
        _bounded_text(entry, "object detail dependency", 500)
    if not isinstance(typed, list) or len(typed) > 2_000:
        raise ObjectDetailError("object detail typed relations must be a bounded list")
    for relation in typed:
        if not isinstance(relation, dict) or set(relation) != {"kind", "target"}:
            raise ObjectDetailError("object detail typed relation is malformed")
        _bounded_text(relation["kind"], "object detail relation kind", 120)
        _bounded_text(relation["target"], "object detail relation target", 500)

    provenance = value.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != {"adapter", "locator"}:
        raise ObjectDetailError("object detail provenance is malformed")
    _bounded_text(provenance["adapter"], "object detail provenance adapter", 120)
    _bounded_text(provenance["locator"], "object detail provenance locator", 1_000)

    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ObjectDetailError("object detail must be JSON data") from exc
    if len(encoded) > MAX_DETAIL_BYTES:
        raise ObjectDetailError(
            f"object detail exceeds {MAX_DETAIL_BYTES} encoded bytes"
        )
