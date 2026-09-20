import copy
import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

from axiv.contracts.openapi import OpenAPIDocument
from axiv.contracts.openapi import OpenAPIResponse
from axiv.contracts.openapi import OpenAPISchema
from axiv.contracts.openapi import SchemaFingerprint
from axiv.contracts.openapi import check_openapi_document
from axiv.openapi_check import load_packaged_baseline

BASELINE = files("axiv").joinpath("resources/openapi-rest-subset.json")


def load_fixture() -> dict[str, object]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_packaged_openapi_baseline_loads_all_reviewed_endpoints() -> None:
    baseline = load_packaged_baseline()

    assert len(baseline.paths) == 26
    assert baseline.paths["/events/v1"].get is not None


def test_openapi_fixture_is_compatible_with_static_contracts() -> None:
    payload = load_fixture()
    document = OpenAPIDocument.model_validate(payload)

    report = check_openapi_document(document, baseline=document)

    assert report.compatible is True
    assert report.checked_endpoints == 26
    assert report.issues == []


def test_openapi_check_reports_missing_route() -> None:
    baseline_payload = load_fixture()
    candidate_payload = copy.deepcopy(baseline_payload)
    paths = candidate_payload["paths"]
    assert isinstance(paths, dict)
    del paths["/events/v1"]

    report = check_openapi_document(
        OpenAPIDocument.model_validate(candidate_payload),
        baseline=OpenAPIDocument.model_validate(baseline_payload),
    )

    assert report.compatible is False
    assert any(issue.kind == "missing_path" and issue.path == "/events/v1" for issue in report.issues)


def test_openapi_check_reports_new_required_parameter() -> None:
    baseline_payload = load_fixture()
    candidate_payload = copy.deepcopy(baseline_payload)
    paths = candidate_payload["paths"]
    assert isinstance(paths, dict)
    operation = paths["/events/v1"]["get"]
    operation["parameters"].append({"name": "required", "in": "query", "required": True, "schema": {"type": "string"}})

    report = check_openapi_document(
        OpenAPIDocument.model_validate(candidate_payload),
        baseline=OpenAPIDocument.model_validate(baseline_payload),
    )

    assert report.compatible is False
    assert any(issue.kind == "required_parameters" for issue in report.issues)


def test_openapi_check_reports_response_schema_drift() -> None:
    baseline_payload = load_fixture()
    candidate_payload = copy.deepcopy(baseline_payload)
    paths = candidate_payload["paths"]
    assert isinstance(paths, dict)
    schema = paths["/papers/v3/{unresolved}/metrics"]["get"]["responses"]["200"]["schema"]
    schema["required"] = ["commentsCount"]

    report = check_openapi_document(
        OpenAPIDocument.model_validate(candidate_payload),
        baseline=OpenAPIDocument.model_validate(baseline_payload),
    )

    assert report.compatible is False
    assert any(issue.kind == "response_schema" for issue in report.issues)


@pytest.mark.parametrize("response_location", ["schema", "content"])
@pytest.mark.parametrize(
    ("baseline_schema", "candidate_schema", "compatible"),
    [
        pytest.param(
            {},
            {"type": None, "$ref": None, "required": [], "allOf": [], "items": None},
            True,
            id="explicit-defaults",
        ),
        pytest.param(
            {"allOf": [{"$ref": "#/Example"}]},
            {"all_of": [{"ref": "#/Example"}]},
            True,
            id="field-names-and-aliases",
        ),
        pytest.param(
            {"type": "array", "items": {"allOf": [{"type": "object"}]}},
            {
                "type": "array",
                "description": "ignored",
                "items": {"allOf": [{"type": "object", "properties": {"future": {"type": "string"}}}]},
            },
            True,
            id="ignored-additive-fields",
        ),
        pytest.param({"items": {}}, {"items": {"required": []}}, True, id="nested-defaults"),
        pytest.param({"type": "object"}, {"type": "string"}, False, id="type-change"),
        pytest.param({"$ref": "#/Example"}, {"$ref": "#/Changed"}, False, id="ref-change"),
        pytest.param({"required": ["a", "b"]}, {"required": ["b", "a"]}, False, id="required-order"),
        pytest.param(
            {"allOf": [{"type": "object"}, {"$ref": "#/Example"}]},
            {"allOf": [{"$ref": "#/Example"}, {"type": "object"}]},
            False,
            id="all-of-order",
        ),
        pytest.param(
            {"items": {"required": ["a"]}},
            {"items": {"required": ["b"]}},
            False,
            id="nested-items-change",
        ),
        pytest.param(
            {"allOf": [{"items": {"$ref": "#/Example"}}]},
            {"allOf": [{"items": {"$ref": "#/Changed"}}]},
            False,
            id="nested-all-of-change",
        ),
    ],
)
def test_schema_comparison_preserves_drift_policy(baseline_schema, candidate_schema, compatible, response_location):
    path = "/papers/v3/{unresolved}/metrics"
    baseline = load_packaged_baseline()
    candidate = baseline.model_copy(deep=True)
    baseline_operation = baseline.paths[path].get
    candidate_operation = candidate.paths[path].get
    assert baseline_operation is not None
    assert candidate_operation is not None
    baseline_operation.responses["200"] = OpenAPIResponse.model_validate({"schema": baseline_schema})
    candidate_response = (
        {"schema": candidate_schema}
        if response_location == "schema"
        else {"content": {"application/json": {"schema": candidate_schema}}}
    )
    candidate_operation.responses["200"] = OpenAPIResponse.model_validate(candidate_response)

    report = check_openapi_document(candidate, baseline=baseline)

    assert report.model_dump() == {
        "compatible": compatible,
        "checked_endpoints": 26,
        "issues": []
        if compatible
        else [{"kind": "response_schema", "path": path, "detail": "HTTP 200 schema changed"}],
    }


def test_schema_fingerprint_remains_importable_and_preserves_conversion():
    schema = OpenAPISchema.model_validate(
        {"type": "array", "items": {"allOf": [{"$ref": "#/Example", "required": ["id"]}]}}
    )
    fingerprint = SchemaFingerprint.from_schema(schema)

    assert fingerprint.model_dump() == schema.model_dump()
    assert isinstance(fingerprint.items, SchemaFingerprint)
    assert isinstance(fingerprint.items.all_of[0], SchemaFingerprint)
    assert fingerprint.model_config["frozen"] is True
    with pytest.raises(ValidationError):
        SchemaFingerprint.model_validate({"unknown": True})
