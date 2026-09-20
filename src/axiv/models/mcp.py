from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import AnyHttpUrl
from pydantic import ConfigDict
from pydantic import Field
from pydantic import JsonValue
from pydantic import StringConstraints
from pydantic import field_validator
from pydantic import model_validator

from axiv.models.common import StrictModel
from axiv.sensitive import contains_sensitive_key

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
PaperValues = Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=50)]


def _reject_controls(value: str, *, label: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        msg = f"{label} must not contain control characters"
        raise ValueError(msg)
    return value


class McpArguments(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def reject_control_characters(self) -> "McpArguments":
        for field_name, value in self.__dict__.items():
            values = value if isinstance(value, tuple) else (value,)
            for item in values:
                if isinstance(item, str):
                    _reject_controls(item, label=field_name)
        return self


class DiscoverPrioritize(StrEnum):
    HISTORICAL = "historical"
    DEFAULT = "default"
    RECENCY = "recency"
    POPULAR = "popular"


class DiscoverPapersArguments(McpArguments):
    keywords: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=20)]
    question: NonEmptyText
    difficulty: float = Field(ge=1, le=10)
    published_after: date | None = None
    published_before: date | None = None
    prioritize: DiscoverPrioritize = DiscoverPrioritize.DEFAULT

    @model_validator(mode="after")
    def validate_values(self) -> "DiscoverPapersArguments":
        for keyword in self.keywords:
            _reject_controls(keyword, label="keyword")
        _reject_controls(self.question, label="question")
        if self.published_after and self.published_before and self.published_after > self.published_before:
            msg = "published_after must not be later than published_before"
            raise ValueError(msg)
        return self


class GetPaperContentArguments(McpArguments):
    url: AnyHttpUrl
    full_text: bool = Field(default=False, alias="fullText")

    @field_validator("url")
    @classmethod
    def validate_paper_host(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        allowed_hosts = {"arxiv.org", "www.arxiv.org", "alphaxiv.org", "www.alphaxiv.org"}
        if value.scheme != "https" or value.host not in allowed_hosts:
            msg = "paper URL must use HTTPS on arxiv.org or alphaxiv.org"
            raise ValueError(msg)
        return value


class AnswerPdfQueriesArguments(McpArguments):
    paper: Identifier
    queries: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def validate_values(self) -> "AnswerPdfQueriesArguments":
        _reject_controls(self.paper, label="paper")
        for query in self.queries:
            _reject_controls(query, label="query")
        return self


class GithubRepositoryArguments(McpArguments):
    github_url: AnyHttpUrl = Field(alias="githubUrl")
    path: NonEmptyText

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https" or value.host not in {"github.com", "www.github.com"}:
            msg = "repository URL must use HTTPS on github.com"
            raise ValueError(msg)
        path_parts = (value.path or "").strip("/").split("/")
        if len(path_parts) != 2 or value.query or value.fragment or value.username or value.password:
            msg = "repository URL must identify only a GitHub owner and repository"
            raise ValueError(msg)
        return value

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _reject_controls(value, label="path")


class ListLibraryArguments(McpArguments):
    include_papers: bool = False
    paper_ids_or_urls: Annotated[tuple[Identifier, ...], Field(max_length=50)] = ()


class SavePapersArguments(McpArguments):
    paper_ids_or_urls: PaperValues
    folder_id: Identifier | None = None


class RemovePapersArguments(McpArguments):
    paper_ids_or_urls: PaperValues
    folder_id: Identifier


class MovePapersArguments(McpArguments):
    paper_ids_or_urls: PaperValues
    from_folder_id: Identifier
    to_folder_id: Identifier

    @model_validator(mode="after")
    def validate_distinct_folders(self) -> "MovePapersArguments":
        if self.from_folder_id == self.to_folder_id:
            msg = "source and target folders must be different"
            raise ValueError(msg)
        return self


class CreateFolderArguments(McpArguments):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    parent_folder_id: Identifier | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _reject_controls(value, label="folder name")


class RenameFolderArguments(McpArguments):
    folder_id: Identifier
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _reject_controls(value, label="folder name")


class DeleteFolderArguments(McpArguments):
    folder_id: Identifier


class McpInitializeResult(StrictModel):
    protocol_version: str
    server_name: str
    server_version: str | None = None


class McpToolDescription(StrictModel):
    name: str
    description: str | None = None
    required_arguments: tuple[str, ...]
    argument_names: tuple[str, ...]


class McpToolList(StrictModel):
    tools: tuple[McpToolDescription, ...]


class McpToolDriftIssue(StrictModel):
    kind: str
    tool: str
    detail: str


class McpToolDriftReport(StrictModel):
    compatible: bool
    checked_tools: int = Field(ge=0)
    issues: tuple[McpToolDriftIssue, ...]


class McpTextResult(StrictModel):
    tool: str
    text: str
    is_error: bool = False
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_sensitive_metadata(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if contains_sensitive_key(value):
            msg = "MCP metadata must not contain sensitive fields"
            raise ValueError(msg)
        return value


class AuthStatusResult(StrictModel):
    api_key_present: bool
    initialized: bool
    tools_compatible: bool
    protocol_version: str | None = None
    server_name: str | None = None
    issue_count: int = Field(default=0, ge=0)
