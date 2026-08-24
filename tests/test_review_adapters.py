import pytest

from vizzer.review_adapters import ReviewAdapterError, parse_adapter_registry, validate_plan_adapters
from vizzer.review_contract import parse_plan
from test_review_contract import plan


def registry():
    return parse_adapter_registry({
        "schema": 1,
        "adapters": [{
            "id": "browser",
            "modes": ["browser"],
            "operations": [{
                "id": "open-route",
                "requiredInputs": ["route"],
                "optionalInputs": ["viewport"],
            }],
        }],
    })


def test_registry_validates_symbolic_operation_without_executable_text():
    candidate = parse_plan(plan())
    assert validate_plan_adapters(candidate, registry()) is candidate
    assert "command" not in registry()["adapters"][0]["operations"][0]


def test_adapter_requests_need_trusted_declarations_and_exact_inputs():
    candidate = parse_plan(plan())
    with pytest.raises(ReviewAdapterError, match="adapters_path"):
        validate_plan_adapters(candidate, None)
    candidate["rows"][0]["steps"][0]["inputs"]["credential"] = "secret"
    with pytest.raises(ReviewAdapterError, match="credential"):
        validate_plan_adapters(candidate, registry())


def test_registry_rejects_command_shaped_extension_fields():
    value = {
        "schema": 1,
        "adapters": [{
            "id": "command",
            "modes": ["command"],
            "operations": [{
                "id": "test",
                "requiredInputs": [],
                "argv": ["sh", "-c", "anything"],
            }],
        }],
    }
    with pytest.raises(ReviewAdapterError, match="argv"):
        parse_adapter_registry(value)
