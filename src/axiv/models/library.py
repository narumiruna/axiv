from typing import Self

from pydantic import AliasChoices
from pydantic import Field
from pydantic import JsonValue
from pydantic import field_validator

from axiv.models.common import ExternalModel
from axiv.models.common import StrictModel
from axiv.sensitive import contains_sensitive_key


class ExternalLibraryPaper(ExternalModel):
    paper_id: str = Field(
        validation_alias=AliasChoices(
            "paper_id",
            "paperId",
            "universal_paper_id",
            "universalPaperId",
            "universal_id",
            "universalId",
            "id",
        )
    )
    title: str | None = None
    url: str | None = None


class ExternalLibraryFolder(ExternalModel):
    folder_id: str = Field(validation_alias=AliasChoices("folder_id", "folderId", "id"))
    name: str
    type: str
    parent_id: str | None = Field(default=None, validation_alias=AliasChoices("parent_id", "parentId"))
    sharing_status: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sharing_status", "sharingStatus"),
    )
    paper_count: int = Field(default=0, ge=0, validation_alias=AliasChoices("paper_count", "paperCount"))
    papers: list[ExternalLibraryPaper] = Field(default_factory=list)


class ExternalPaperMembership(ExternalModel):
    paper_id: str = Field(
        validation_alias=AliasChoices(
            "paper_id",
            "paperId",
            "universal_paper_id",
            "universalPaperId",
            "paper",
            "id",
        )
    )
    folder_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("folder_ids", "folderIds", "folders", "in_folders", "inFolders"),
    )


class ExternalLibraryResponse(ExternalModel):
    folders: list[ExternalLibraryFolder]
    paper_membership: list[ExternalPaperMembership] = Field(
        default_factory=list,
        validation_alias=AliasChoices("paper_membership", "paperMembership", "memberships"),
    )


class LibraryPaper(StrictModel):
    paper_id: str
    title: str | None = None
    url: str | None = None

    @classmethod
    def from_external(cls, paper: ExternalLibraryPaper) -> Self:
        return cls(paper_id=paper.paper_id, title=paper.title, url=paper.url)


class LibraryFolder(StrictModel):
    folder_id: str
    name: str
    type: str
    parent_id: str | None = None
    sharing_status: str | None = None
    paper_count: int = Field(ge=0)
    papers: tuple[LibraryPaper, ...] = ()

    @classmethod
    def from_external(cls, folder: ExternalLibraryFolder) -> Self:
        return cls(
            folder_id=folder.folder_id,
            name=folder.name,
            type=folder.type,
            parent_id=folder.parent_id,
            sharing_status=folder.sharing_status,
            paper_count=folder.paper_count,
            papers=tuple(LibraryPaper.from_external(paper) for paper in folder.papers),
        )


class PaperMembership(StrictModel):
    paper_id: str
    folder_ids: tuple[str, ...]

    @classmethod
    def from_external(cls, membership: ExternalPaperMembership) -> Self:
        return cls(paper_id=membership.paper_id, folder_ids=tuple(membership.folder_ids))


class LibraryListResult(StrictModel):
    folders: tuple[LibraryFolder, ...]
    memberships: tuple[PaperMembership, ...]

    @classmethod
    def from_external(cls, response: ExternalLibraryResponse) -> Self:
        return cls(
            folders=tuple(LibraryFolder.from_external(folder) for folder in response.folders),
            memberships=tuple(PaperMembership.from_external(item) for item in response.paper_membership),
        )


class LibraryMutationResult(StrictModel):
    action: str
    success: bool
    target: str
    affected_count: int | None = Field(default=None, ge=0)
    message: str | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def reject_sensitive_details(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if contains_sensitive_key(value):
            msg = "library result details must not contain sensitive fields"
            raise ValueError(msg)
        return value
