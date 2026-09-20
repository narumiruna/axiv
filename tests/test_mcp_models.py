import json
from datetime import date

import pytest
from pydantic import ValidationError

from axiv.models.library import ExternalLibraryResponse
from axiv.models.library import LibraryFolder
from axiv.models.library import LibraryListResult
from axiv.models.library import LibraryMutationResult
from axiv.models.mcp import AnswerPdfQueriesArguments
from axiv.models.mcp import AuthStatusResult
from axiv.models.mcp import CreateFolderArguments
from axiv.models.mcp import DiscoverPapersArguments
from axiv.models.mcp import GithubRepositoryArguments
from axiv.models.mcp import McpTextResult
from axiv.models.mcp import RenameFolderArguments
from axiv.models.mcp import SavePapersArguments


def test_discover_arguments_validate_bounds_dates_and_alias_serialization() -> None:
    arguments = DiscoverPapersArguments(
        keywords=("attention",),
        question="How does attention work?",
        difficulty=5,
        published_after=date(2017, 1, 1),
        prioritize="historical",
    )

    assert arguments.model_dump(by_alias=True, exclude_none=True, mode="json") == {
        "keywords": ["attention"],
        "question": "How does attention work?",
        "difficulty": 5,
        "published_after": "2017-01-01",
        "prioritize": "historical",
    }
    with pytest.raises(ValidationError):
        DiscoverPapersArguments(keywords=("attention",), question="Question", difficulty=11)


@pytest.mark.parametrize("control", [*range(32), 127])
@pytest.mark.parametrize(
    ("model", "values", "field"),
    [
        (DiscoverPapersArguments, {"keywords": ("topic",), "question": "Question", "difficulty": 5}, "keywords"),
        (DiscoverPapersArguments, {"keywords": ("topic",), "question": "Question", "difficulty": 5}, "question"),
        (AnswerPdfQueriesArguments, {"paper": "paper", "queries": ("Question",)}, "paper"),
        (AnswerPdfQueriesArguments, {"paper": "paper", "queries": ("Question",)}, "queries"),
    ],
)
def test_research_control_errors_preserve_messages_and_locations(model, values, field, control):
    invalid = f"a{chr(control)}b"
    payload = {**values, field: ("valid", invalid) if isinstance(values[field], tuple) else invalid}

    with pytest.raises(ValidationError) as captured:
        model.model_validate(payload)

    assert captured.value.errors(include_url=False, include_context=False) == [
        {
            "type": "value_error",
            "loc": (),
            "msg": f"Value error, {field} must not contain control characters",
            "input": payload,
        }
    ]


@pytest.mark.parametrize(
    ("after", "before", "valid"),
    [
        (None, None, True),
        ("2026-01-01", None, True),
        (None, "2026-01-01", True),
        ("2026-01-01", "2026-01-01", True),
        ("2026-01-01", "2026-02-01", True),
        ("2026-02-01", "2026-01-01", False),
    ],
)
def test_discovery_date_range_validation_remains_independent(after, before, valid):
    payload = {
        "keywords": (" topic ",),
        "question": " Question ",
        "difficulty": 5,
        "published_after": after,
        "published_before": before,
    }
    if valid:
        result = DiscoverPapersArguments.model_validate(payload)
        assert result.keywords == ("topic",)
        assert result.question == "Question"
    else:
        with pytest.raises(ValidationError) as captured:
            DiscoverPapersArguments.model_validate(payload)
        assert captured.value.errors(include_url=False, include_context=False) == [
            {
                "type": "value_error",
                "loc": (),
                "msg": "Value error, published_after must not be later than published_before",
                "input": payload,
            }
        ]


@pytest.mark.parametrize(
    ("model", "payload", "field", "label"),
    [
        (GithubRepositoryArguments, {"githubUrl": "https://github.com/owner/repo", "path": "a\u001bb"}, "path", "path"),
        (CreateFolderArguments, {"name": "a\u001bb"}, "name", "folder name"),
        (RenameFolderArguments, {"folder_id": "folder", "name": "a\u001bb"}, "name", "folder name"),
    ],
)
def test_control_field_validators_preserve_error_precedence(model, payload, field, label):
    with pytest.raises(ValidationError) as captured:
        model.model_validate(payload)
    error = captured.value.errors()[0]
    assert error["loc"] == (field,)
    assert error["msg"] == f"Value error, {label} must not contain control characters"


def test_research_arguments_reject_empty_or_unsafe_values() -> None:
    with pytest.raises(ValidationError):
        AnswerPdfQueriesArguments(paper="1706.03762", queries=())
    with pytest.raises(ValidationError):
        GithubRepositoryArguments(github_url="https://example.com/repo", path="/")
    with pytest.raises(ValidationError):
        GithubRepositoryArguments(github_url="https://github.com/owner/repo/issues/1", path="/")
    with pytest.raises(ValidationError):
        GithubRepositoryArguments(github_url="https://github.com/owner/repo?tab=readme", path="/")
    with pytest.raises(ValidationError):
        GithubRepositoryArguments(github_url="https://github.com/owner/repo", path="bad\x1bpath")


def test_library_arguments_enforce_remote_limits_and_folder_names() -> None:
    arguments = SavePapersArguments(folder_id="folder-1", paper_ids_or_urls=("1706.03762",))

    assert arguments.model_dump(by_alias=True, exclude_none=True, mode="json") == {
        "paper_ids_or_urls": ["1706.03762"],
        "folder_id": "folder-1",
    }
    with pytest.raises(ValidationError):
        SavePapersArguments(folder_id="folder-1", paper_ids_or_urls=tuple(str(index) for index in range(51)))
    with pytest.raises(ValidationError):
        CreateFolderArguments(name="  ")
    with pytest.raises(ValidationError):
        SavePapersArguments(folder_id="folder-1\x00", paper_ids_or_urls=("1706.03762",))
    with pytest.raises(ValidationError):
        SavePapersArguments(folder_id="folder-1", paper_ids_or_urls=("1706.03762\x1b",))


def test_external_library_models_tolerate_additive_fields_but_stable_output_is_strict() -> None:
    external = ExternalLibraryResponse.model_validate(
        {
            "folders": [
                {
                    "folder_id": "folder-1",
                    "name": "Reading",
                    "type": "custom",
                    "paper_count": 1,
                    "future_remote_field": True,
                }
            ],
            "future_top_level_field": "ignored",
        }
    )
    stable = LibraryListResult(
        folders=tuple(LibraryFolder.from_external(folder) for folder in external.folders),
        memberships=(),
    )

    assert json.loads(stable.model_dump_json())["folders"][0]["folder_id"] == "folder-1"
    with pytest.raises(ValidationError):
        LibraryListResult.model_validate({"folders": [], "memberships": [], "unknown": True})


def test_library_models_accept_live_paper_and_membership_field_names() -> None:
    external = ExternalLibraryResponse.model_validate(
        {
            "folders": [
                {
                    "folder_id": "folder-1",
                    "name": "Reading",
                    "type": "custom",
                    "paper_count": 1,
                    "papers": [{"universal_paper_id": "1706.03762", "title": "Attention Is All You Need"}],
                }
            ],
            "paper_membership": [{"universal_paper_id": "1706.03762", "in_folders": ["folder-1"]}],
        }
    )
    stable = LibraryListResult.from_external(external)

    assert stable.folders[0].papers[0].paper_id == "1706.03762"
    assert stable.memberships[0].paper_id == "1706.03762"
    assert stable.memberships[0].folder_ids == ("folder-1",)


def test_mcp_outputs_never_have_an_api_key_field() -> None:
    status = AuthStatusResult(
        api_key_present=True,
        initialized=True,
        tools_compatible=True,
        protocol_version="2025-03-26",
        server_name="alphaXiv",
    )
    result = McpTextResult(tool="discover_papers", text="answer", metadata={"requestId": "request-1"})

    serialized = status.model_dump_json() + result.model_dump_json()
    assert "axv-" not in serialized
    assert 'api_key"' not in serialized


def test_mcp_outputs_preserve_safe_keys_and_scalar_values() -> None:
    nested = {"data": [{"token_count": 2, "api_key_present": True, "secretary": None, "text": "Authorization"}]}
    text = McpTextResult(tool="discover_papers", text="answer", metadata=nested)
    mutation = LibraryMutationResult(action="create_folder", success=True, target="Reading", details=nested)

    assert text.metadata == nested
    assert mutation.details == nested


@pytest.mark.parametrize(
    "sensitive_key",
    ["apiKey", "access_token", "client-secret", "sessionCookie", "Authorization"],
)
def test_mcp_outputs_reject_nested_sensitive_fields(sensitive_key: str) -> None:
    nested = {"data": [{sensitive_key: "axv-private"}]}

    with pytest.raises(ValidationError):
        McpTextResult(tool="discover_papers", text="answer", metadata=nested)
    with pytest.raises(ValidationError):
        LibraryMutationResult(
            action="create_folder",
            success=True,
            target="Reading",
            details=nested,
        )
