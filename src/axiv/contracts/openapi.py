from __future__ import annotations

from pydantic import ConfigDict
from pydantic import Field

from axiv.contracts.rest import ENDPOINTS
from axiv.models.common import ExternalModel
from axiv.models.common import StrictModel


class OpenAPISchema(ExternalModel):
    type: str | None = None
    ref: str | None = Field(default=None, alias="$ref")
    required: tuple[str, ...] = ()
    all_of: tuple[OpenAPISchema, ...] = Field(default=(), alias="allOf")
    items: OpenAPISchema | None = None


class OpenAPIParameter(ExternalModel):
    name: str
    location: str = Field(alias="in")
    required: bool = False
    schema_value: OpenAPISchema = Field(default_factory=OpenAPISchema, alias="schema")


class OpenAPIMediaType(ExternalModel):
    schema_value: OpenAPISchema = Field(default_factory=OpenAPISchema, alias="schema")


class OpenAPIResponse(ExternalModel):
    schema_value: OpenAPISchema | None = Field(default=None, alias="schema")
    content: dict[str, OpenAPIMediaType] = Field(default_factory=dict)

    def json_schema(self) -> OpenAPISchema:
        if self.schema_value is not None:
            return self.schema_value
        media_type = self.content.get("application/json")
        return media_type.schema_value if media_type is not None else OpenAPISchema()


class OpenAPIOperation(ExternalModel):
    parameters: tuple[OpenAPIParameter, ...] = ()
    responses: dict[str, OpenAPIResponse]


class OpenAPIPathItem(ExternalModel):
    get: OpenAPIOperation | None = None


class OpenAPIInfo(ExternalModel):
    title: str
    version: str


class OpenAPIDocument(ExternalModel):
    openapi: str
    info: OpenAPIInfo
    paths: dict[str, OpenAPIPathItem]


class SchemaFingerprint(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str | None = None
    ref: str | None = None
    required: tuple[str, ...] = ()
    all_of: tuple[SchemaFingerprint, ...] = ()
    items: SchemaFingerprint | None = None

    @classmethod
    def from_schema(cls, schema: OpenAPISchema) -> SchemaFingerprint:
        return cls(
            type=schema.type,
            ref=schema.ref,
            required=schema.required,
            all_of=tuple(cls.from_schema(item) for item in schema.all_of),
            items=cls.from_schema(schema.items) if schema.items is not None else None,
        )


class DriftIssue(StrictModel):
    kind: str
    path: str
    detail: str


class OpenAPIDriftReport(StrictModel):
    compatible: bool
    checked_endpoints: int = Field(ge=0)
    issues: list[DriftIssue]


def check_openapi_document(
    candidate: OpenAPIDocument,
    *,
    baseline: OpenAPIDocument,
) -> OpenAPIDriftReport:
    issues: list[DriftIssue] = []
    for endpoint in ENDPOINTS.values():
        candidate_path = candidate.paths.get(endpoint.path)
        if candidate_path is None:
            issues.append(DriftIssue(kind="missing_path", path=endpoint.path, detail="GET path is missing"))
            continue
        operation = candidate_path.get
        if operation is None:
            issues.append(DriftIssue(kind="missing_method", path=endpoint.path, detail="GET operation is missing"))
            continue

        actual_required = {
            (parameter.location, parameter.name) for parameter in operation.parameters if parameter.required
        }
        expected_required = {
            *(("path", name) for name in endpoint.required_path_params),
            *(("query", name) for name in endpoint.required_query_params),
        }
        if actual_required != expected_required:
            issues.append(
                DriftIssue(
                    kind="required_parameters",
                    path=endpoint.path,
                    detail="required parameters changed",
                )
            )

        actual_parameters = {(parameter.location, parameter.name) for parameter in operation.parameters}
        expected_optional = {("query", name) for name in endpoint.optional_query_params}
        missing_optional = expected_optional - actual_parameters
        if missing_optional:
            issues.append(
                DriftIssue(
                    kind="missing_optional_parameters",
                    path=endpoint.path,
                    detail="reviewed optional parameters are missing",
                )
            )

        baseline_path = baseline.paths.get(endpoint.path)
        baseline_operation = baseline_path.get if baseline_path is not None else None
        if baseline_operation is None:
            issues.append(
                DriftIssue(kind="missing_baseline", path=endpoint.path, detail="baseline operation is missing")
            )
            continue
        candidate_response = operation.responses.get("200")
        baseline_response = baseline_operation.responses.get("200")
        if candidate_response is None or baseline_response is None:
            issues.append(DriftIssue(kind="response_schema", path=endpoint.path, detail="HTTP 200 schema is missing"))
            continue
        if candidate_response.json_schema() != baseline_response.json_schema():
            issues.append(DriftIssue(kind="response_schema", path=endpoint.path, detail="HTTP 200 schema changed"))

    return OpenAPIDriftReport(
        compatible=not issues,
        checked_endpoints=len(ENDPOINTS),
        issues=issues,
    )
