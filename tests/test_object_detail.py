import copy

import pytest

from vizzer.model import Item, Relation
from vizzer.object_detail import (
    MAX_DETAIL_BYTES,
    ObjectDetailError,
    object_detail_for,
    validate_object_detail,
)


def test_object_detail_is_source_format_neutral_and_injects_sections():
    item = Item(
        id="service:catalog",
        title="Catalog API",
        one_liner="Lists published products.",
        status="building",
        release="R1",
        role="delivery",
        tags=["public-api"],
        facets={"runtime": ["edge"]},
        deps=["database:catalog"],
        relations=[Relation(kind="tested-by", target="test:catalog-contract")],
        source={"adapter": "service-manifest", "path": "services/catalog.yaml"},
    )

    detail = object_detail_for(item, sections={
        "reviewSteps": ["Request the list endpoint."],
        "acceptance": {"status": 200},
        "definitionOfDone": ["The response matches the public schema."],
    })

    assert detail["schema"] == "vizzer-object-detail/v1"
    assert detail["sections"]["acceptance"] == {"status": 200}
    assert detail["relationships"]["dependsOn"] == ["database:catalog"]
    assert detail["provenance"] == {
        "adapter": "service-manifest",
        "locator": "services/catalog.yaml",
    }


def test_object_detail_rejects_unknown_sections_and_encoded_bloat():
    detail = object_detail_for(Item(id="job:daily", title="Daily job"))
    unknown = copy.deepcopy(detail)
    unknown["sections"]["surprise"] = "not contracted"
    with pytest.raises(ObjectDetailError, match="unknown names"):
        validate_object_detail(unknown)

    oversized = copy.deepcopy(detail)
    oversized["sections"]["acceptance"] = "x" * (MAX_DETAIL_BYTES + 1)
    with pytest.raises(ObjectDetailError, match="encoded bytes"):
        validate_object_detail(oversized)
