from enum import StrEnum
from typing import Self

from pydantic import Field
from pydantic import JsonValue
from pydantic import model_validator

from axiv.models.common import ExternalModel
from axiv.models.common import ItemCollection
from axiv.models.common import StrictModel


class PaperSummary(ExternalModel):
    summary: str
    original_problem: list[str] = Field(default_factory=list, alias="originalProblem")
    solution: list[str] = Field(default_factory=list)
    key_insights: list[str] = Field(default_factory=list, alias="keyInsights")
    results: list[str] = Field(default_factory=list)


class PaperPreview(ExternalModel):
    id: str
    paper_group_id: str = Field(alias="paper_group_id")
    title: str
    abstract: str
    universal_paper_id: str = Field(alias="universal_paper_id")
    version_id: str = Field(alias="version_id")
    canonical_id: str | None = Field(default=None, alias="canonical_id")
    authors: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    publication_date: str | None = Field(default=None, alias="publication_date")
    paper_summary: PaperSummary | None = Field(default=None, alias="paper_summary")
    github_url: str | None = Field(default=None, alias="github_url")


class PaperRecord(ExternalModel):
    type: str
    group_id: str = Field(alias="groupId")
    version_id: str = Field(alias="versionId")
    universal_id: str = Field(alias="universalId")
    version_label: str = Field(alias="versionLabel")
    version_order: int = Field(alias="versionOrder", ge=1)
    title: str
    abstract: str
    publication_date: int | float | None = Field(default=None, alias="publicationDate")
    first_publication_date: int | float | None = Field(default=None, alias="firstPublicationDate")
    license: str | None = None
    citation_bibtex: str | None = Field(default=None, alias="citationBibtex")
    source_url: str | None = Field(default=None, alias="sourceUrl")


class ResolvedPaperIdentifiers(StrictModel):
    universal_id: str
    group_id: str
    version_id: str

    @classmethod
    def from_record(cls, record: PaperRecord) -> Self:
        return cls(
            universal_id=record.universal_id,
            group_id=record.group_id,
            version_id=record.version_id,
        )


class LegacyPaperVersion(ExternalModel):
    id: str
    universal_paper_id: str = Field(alias="universal_paper_id")
    title: str
    abstract: str
    version_label: str | None = Field(default=None, alias="version_label")


class LegacyPaperGroup(ExternalModel):
    id: str
    universal_paper_id: str = Field(alias="universal_paper_id")


class LegacyPaperContainer(ExternalModel):
    paper_version: LegacyPaperVersion = Field(alias="paper_version")
    paper_group: LegacyPaperGroup = Field(alias="paper_group")


class CommentEndorsement(ExternalModel):
    id: str
    name: str


class CommentAuthor(ExternalModel):
    id: str
    username: str
    real_name: str = Field(alias="realName")
    researcher_slug: str | None = Field(default=None, alias="researcherSlug")


class PaperComment(ExternalModel):
    id: str
    author: CommentAuthor
    title: str | None = None
    body: str
    date: str
    upvotes: int = 0
    universal_id: str = Field(alias="universalId")
    paper_group_id: str = Field(alias="paperGroupId")
    paper_version_id: str = Field(alias="paperVersionId")
    parent_comment_id: str | None = Field(default=None, alias="parentCommentId")
    endorsements: list[CommentEndorsement] = Field(default_factory=list)
    responses: list["PaperComment"] = Field(default_factory=list)


class LegacyPaperResponse(ExternalModel):
    paper: LegacyPaperContainer
    comments: list[PaperComment] = Field(default_factory=list)


class PaperComments(ItemCollection[PaperComment]):
    pass


class SimilarPapers(ItemCollection[PaperPreview]):
    pass


class PaperPage(ExternalModel):
    page_number: int = Field(alias="pageNumber", ge=1)
    text: str


class FullTextResponse(ExternalModel):
    pages: list[PaperPage]


class OverviewResponse(ExternalModel):
    title: str
    abstract: str
    summary: PaperSummary | None = None
    overview: str
    intermediate_report: str | None = Field(default=None, alias="intermediateReport")
    citations: list[JsonValue] = Field(default_factory=list)
    summary_section_titles: dict[str, JsonValue] = Field(default_factory=dict, alias="summarySectionTitles")
    overview_section_titles: dict[str, JsonValue] = Field(default_factory=dict, alias="overviewSectionTitles")


class TranslationStatus(ExternalModel):
    state: str
    requested_at: int | float | None = Field(default=None, alias="requestedAt")
    updated_at: int | float | None = Field(default=None, alias="updatedAt")
    error: JsonValue | None = None


class OverviewStatus(ExternalModel):
    state: str
    updated_at: int | float = Field(alias="updatedAt")
    translations: dict[str, TranslationStatus]


class PaperMetrics(ExternalModel):
    comments_count: int = Field(alias="commentsCount", ge=0)
    public_total_votes: int = Field(alias="publicTotalVotes")
    visits_all: int = Field(alias="visitsAll", ge=0)


class FiguresResponse(ExternalModel):
    figures: list[str]


class PaperLink(ExternalModel):
    id: str
    label: str
    url: str


class ExtrasResponse(ExternalModel):
    links: list[PaperLink]
    repo_url: str | None = Field(alias="repoUrl")
    autoresearch: bool
    featured_tweets: JsonValue | None = Field(alias="featuredTweets")


class Implementation(ExternalModel):
    id: str
    type: str
    url: str
    title: str | None = None
    description: str | None = None
    source: str | None = None
    language: str | None = None
    stars: int | None = None


class ImplementationsResponse(ExternalModel):
    alphaxiv_implementations: list[Implementation] = Field(alias="alphaXivImplementations")
    paper_resources: list[Implementation] = Field(alias="paperResources")


class AutoresearchImplementationsResponse(ExternalModel):
    implementations: list[Implementation]


class AIDetectionWindow(ExternalModel):
    text: str
    label: str
    ai_assistance_score: float = Field(alias="aiAssistanceScore")
    confidence: str
    page_index: int = Field(alias="pageIndex", ge=0)
    start_index: int = Field(alias="startIndex", ge=0)
    end_index: int = Field(alias="endIndex", ge=0)


class AIDetectionResponse(ExternalModel):
    state: str
    fraction_ai: float | None = Field(alias="fractionAi")
    fraction_ai_assisted: float | None = Field(alias="fractionAiAssisted")
    fraction_human: float | None = Field(alias="fractionHuman")
    prediction_short: str | None = Field(alias="predictionShort")
    headline: str | None = None
    windows: list[AIDetectionWindow]
    updated_at: int | float = Field(alias="updatedAt")


class ModelReference(ExternalModel):
    id: str
    model_id: str = Field(alias="modelId")
    provider_name: str = Field(alias="providerName")
    model_name: str = Field(alias="modelName")
    description: str | None = None
    release_date: int | float | None = Field(default=None, alias="releaseDate")


class ModelMatch(ExternalModel):
    matched_text: str = Field(alias="matchedText")
    page_index: int = Field(alias="pageIndex", ge=0)
    start_index: int = Field(alias="startIndex", ge=0)
    end_index: int = Field(alias="endIndex", ge=0)
    model: ModelReference


class ModelLinksResponse(ExternalModel):
    state: str
    matches: list[ModelMatch]
    updated_at: int | float = Field(alias="updatedAt")
    is_outdated: bool = Field(alias="isOutdated")


class RelatedKind(StrEnum):
    COMMENTS = "comments"
    SIMILAR = "similar"
    METRICS = "metrics"
    FIGURES = "figures"
    EXTRAS = "extras"
    IMPLEMENTATIONS = "implementations"
    AUTORESEARCH = "autoresearch"
    AI_DETECTION = "ai-detection"
    MODEL_LINKS = "model-links"


class PaperIdentifier(StrictModel):
    value: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_value(self) -> Self:
        value = self.value
        if value != value.strip():
            msg = "paper identifier must not have surrounding whitespace"
            raise ValueError(msg)
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            msg = "paper identifier must not contain control characters"
            raise ValueError(msg)
        if value in {".", ".."}:
            msg = "paper identifier is invalid"
            raise ValueError(msg)
        return self
