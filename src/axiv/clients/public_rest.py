import json
from collections.abc import Mapping
from types import TracebackType
from urllib.parse import quote

import httpx
from pydantic import BaseModel
from pydantic import ValidationError

from axiv.contracts.rest import API_BASE_URL
from axiv.contracts.rest import ENDPOINTS
from axiv.contracts.rest import EndpointName
from axiv.errors import InvalidResponseError
from axiv.errors import NetworkError
from axiv.errors import map_http_error
from axiv.models.common import RestSettings
from axiv.models.events import Event
from axiv.models.events import EventsResponse
from axiv.models.feed import FeedInterval
from axiv.models.feed import FeedResponse
from axiv.models.feed import FeedSort
from axiv.models.feed import TopicGroupsResponse
from axiv.models.paper import AIDetectionResponse
from axiv.models.paper import AutoresearchImplementationsResponse
from axiv.models.paper import ExtrasResponse
from axiv.models.paper import FiguresResponse
from axiv.models.paper import FullTextResponse
from axiv.models.paper import ImplementationsResponse
from axiv.models.paper import LegacyPaperResponse
from axiv.models.paper import ModelLinksResponse
from axiv.models.paper import OverviewResponse
from axiv.models.paper import OverviewStatus
from axiv.models.paper import PaperComment
from axiv.models.paper import PaperComments
from axiv.models.paper import PaperIdentifier
from axiv.models.paper import PaperMetrics
from axiv.models.paper import PaperPreview
from axiv.models.paper import PaperRecord
from axiv.models.paper import SimilarPapers
from axiv.models.researchers import ResearchersResponse
from axiv.models.search import FullTextSearchResult
from axiv.models.search import FullTextSearchResults
from axiv.models.search import Organization
from axiv.models.search import OrganizationResults
from axiv.models.search import PaperSearchResult
from axiv.models.search import PaperSearchResults
from axiv.models.search import TopicSuggestions


class PublicRestClient:
    """Anonymous alphaXiv REST client with a static, reviewed route surface."""

    MAX_RESPONSE_BYTES = 20 * 1024 * 1024
    MAX_QUERY_LENGTH = 500
    MAX_PAGE_SIZE = 50
    MAX_SIMILAR = 20
    MAX_TOPICS = 20

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        settings: RestSettings | None = None,
    ) -> None:
        self._settings = settings or RestSettings()
        self._owns_client = http_client is None
        if http_client is None:
            self._client = httpx.Client(
                base_url=self._settings.base_url,
                headers={"Accept": "application/json", "User-Agent": "axiv/0.0.0"},
                timeout=self._settings.timeout_seconds,
                follow_redirects=False,
            )
        else:
            base_url = str(http_client.base_url).rstrip("/")
            if base_url != API_BASE_URL:
                msg = "public REST client must use the alphaXiv production API host"
                raise ValueError(msg)
            sensitive = {"authorization", "cookie"}.intersection(http_client.headers)
            if sensitive:
                msg = "public REST client cannot use sensitive headers"
                raise ValueError(msg)
            if http_client.follow_redirects:
                msg = "public REST client cannot follow redirects"
                raise ValueError(msg)
            self._client = http_client

    def __enter__(self) -> "PublicRestClient":
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search_papers(self, query: str) -> PaperSearchResults:
        payload = self._get_json(
            EndpointName.SEARCH_FAST,
            params={"q": self._query(query), "includePrivate": "false"},
        )
        items = self._parse_list(payload, PaperSearchResult)
        return PaperSearchResults.from_items(items)

    def search_full_text(self, query: str, *, limit: int = 10) -> FullTextSearchResults:
        limit = self._bounded(limit, maximum=self.MAX_PAGE_SIZE, name="limit")
        payload = self._get_json(
            EndpointName.SEARCH_FULL_TEXT,
            params={"q": self._query(query), "limit": str(limit)},
        )
        items = self._parse_list(payload, FullTextSearchResult)
        return FullTextSearchResults.from_items(items)

    def search_rich_papers(self, query: str) -> SimilarPapers:
        payload = self._get_json(EndpointName.SEARCH_RICH, params={"q": self._query(query)})
        items = self._parse_list(payload, PaperPreview)
        return SimilarPapers.from_items(items)

    def closest_topics(self, query: str) -> TopicSuggestions:
        payload = self._get_json(EndpointName.CLOSEST_TOPIC, params={"input": self._query(query)})
        return self._parse_model(payload, TopicSuggestions)

    def search_organizations(self, query: str) -> OrganizationResults:
        payload = self._get_json(EndpointName.SEARCH_ORGANIZATIONS, params={"q": self._query(query)})
        items = self._parse_list(payload, Organization)
        return OrganizationResults.from_items(items)

    def top_organizations(self) -> OrganizationResults:
        payload = self._get_json(EndpointName.TOP_ORGANIZATIONS)
        items = self._parse_list(payload, Organization)
        return OrganizationResults.from_items(items)

    def list_researchers(self, *, offset: int | None = None) -> ResearchersResponse:
        if offset is not None and not 0 <= offset <= 1_000_000:
            msg = "offset must be between 0 and 1000000"
            raise ValueError(msg)
        params = {"offset": str(offset)} if offset is not None else None
        payload = self._get_json(EndpointName.LIST_RESEARCHERS, params=params)
        return self._parse_model(payload, ResearchersResponse)

    def search_researchers(self, query: str) -> ResearchersResponse:
        payload = self._get_json(EndpointName.SEARCH_RESEARCHERS, params={"q": self._query(query)})
        return self._parse_model(payload, ResearchersResponse)

    def list_events(self) -> EventsResponse:
        payload = self._get_json(EndpointName.LIST_EVENTS)
        items = self._parse_list(payload, Event)
        return EventsResponse.from_items(items)

    def feed(
        self,
        *,
        page_num: int = 0,
        page_size: int = 10,
        sort: FeedSort = FeedSort.HOT,
        interval: FeedInterval = FeedInterval.THIRTY_DAYS,
        topics: tuple[str, ...] = (),
    ) -> FeedResponse:
        if not 0 <= page_num <= 10_000:
            msg = "page number must be between 0 and 10000"
            raise ValueError(msg)
        page_size = self._bounded(page_size, maximum=self.MAX_PAGE_SIZE, name="page size")
        if len(topics) > self.MAX_TOPICS:
            msg = f"topics cannot contain more than {self.MAX_TOPICS} values"
            raise ValueError(msg)
        clean_topics = [self._topic(topic) for topic in topics]
        payload = self._get_json(
            EndpointName.FEED,
            params={
                "pageNum": str(page_num),
                "pageSize": str(page_size),
                "sort": sort.value,
                "interval": interval.value,
                "topics": json.dumps(clean_topics, separators=(",", ":")),
            },
        )
        return self._parse_model(payload, FeedResponse)

    def icml_topics(self) -> TopicGroupsResponse:
        return self._get_model(EndpointName.ICML_TOPICS, TopicGroupsResponse)

    def legacy_paper(self, identifier: str) -> LegacyPaperResponse:
        return self._get_model(EndpointName.LEGACY_PAPER, LegacyPaperResponse, unresolved=identifier)

    def paper(self, identifier: str) -> PaperRecord:
        return self._get_model(EndpointName.PAPER, PaperRecord, unresolved=identifier)

    def paper_preview(self, identifier: str) -> PaperPreview:
        return self._get_model(EndpointName.PAPER_PREVIEW, PaperPreview, id=identifier)

    def paper_full_text(self, version_id: str) -> FullTextResponse:
        return self._get_model(EndpointName.PAPER_FULL_TEXT, FullTextResponse, paperVersion=version_id)

    def paper_overview(self, version_id: str, language: str = "en") -> OverviewResponse:
        language = self._language(language)
        return self._get_model(
            EndpointName.PAPER_OVERVIEW,
            OverviewResponse,
            paperVersion=version_id,
            language=language,
        )

    def paper_overview_status(self, version_id: str) -> OverviewStatus:
        return self._get_model(
            EndpointName.PAPER_OVERVIEW_STATUS,
            OverviewStatus,
            paperVersion=version_id,
        )

    def paper_comments(self, group_id: str) -> PaperComments:
        payload = self._get_json(EndpointName.PAPER_COMMENTS, path_values={"group": group_id})
        items = self._parse_list(payload, PaperComment)
        return PaperComments.from_items(items)

    def similar_papers(self, identifier: str, *, limit: int = 10) -> SimilarPapers:
        limit = self._bounded(limit, maximum=self.MAX_SIMILAR, name="limit")
        payload = self._get_json(
            EndpointName.SIMILAR_PAPERS,
            params={"limit": str(limit)},
            path_values={"id": identifier},
        )
        items = self._parse_list(payload, PaperPreview)
        return SimilarPapers.from_items(items)

    def paper_metrics(self, identifier: str) -> PaperMetrics:
        return self._get_model(EndpointName.PAPER_METRICS, PaperMetrics, unresolved=identifier)

    def paper_figures(self, group_id: str) -> FiguresResponse:
        return self._get_model(EndpointName.PAPER_FIGURES, FiguresResponse, paperGroupId=group_id)

    def paper_extras(self, group_id: str) -> ExtrasResponse:
        return self._get_model(EndpointName.PAPER_EXTRAS, ExtrasResponse, paperGroupId=group_id)

    def paper_implementations(self, group_id: str) -> ImplementationsResponse:
        return self._get_model(
            EndpointName.PAPER_IMPLEMENTATIONS,
            ImplementationsResponse,
            paperGroupId=group_id,
        )

    def autoresearch_implementations(self, group_id: str) -> AutoresearchImplementationsResponse:
        return self._get_model(
            EndpointName.AUTORESEARCH_IMPLEMENTATIONS,
            AutoresearchImplementationsResponse,
            paperGroupId=group_id,
        )

    def ai_detection(self, version_id: str) -> AIDetectionResponse:
        return self._get_model(EndpointName.AI_DETECTION, AIDetectionResponse, paperVersion=version_id)

    def model_links(self, version_id: str) -> ModelLinksResponse:
        return self._get_model(EndpointName.MODEL_LINKS, ModelLinksResponse, paperVersion=version_id)

    def _get_model[ModelT: BaseModel](
        self,
        endpoint_name: EndpointName,
        model: type[ModelT],
        **path_values: str,
    ) -> ModelT:
        payload = self._get_json(endpoint_name, path_values=path_values)
        return self._parse_model(payload, model)

    def _get_json(
        self,
        endpoint_name: EndpointName,
        *,
        params: Mapping[str, str] | None = None,
        path_values: Mapping[str, str] | None = None,
    ) -> object:
        endpoint = ENDPOINTS[endpoint_name]
        encoded_values = {
            name: quote(PaperIdentifier(value=value).value, safe="") for name, value in (path_values or {}).items()
        }
        path = endpoint.path.format(**encoded_values)
        self._client.cookies.clear()
        try:
            with self._client.stream("GET", path, params=params) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > self.MAX_RESPONSE_BYTES:
                        msg = "alphaXiv response was too large"
                        raise InvalidResponseError(msg)
                decoded_headers = [
                    (name, value)
                    for name, value in response.headers.multi_items()
                    if name.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
                ]
                buffered = httpx.Response(
                    response.status_code,
                    headers=decoded_headers,
                    content=bytes(body),
                    request=response.request,
                )
        except httpx.RequestError as error:
            raise NetworkError("alphaXiv network request failed") from error
        finally:
            self._client.cookies.clear()
        if buffered.is_error:
            raise map_http_error(buffered)
        content_type = buffered.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise InvalidResponseError("alphaXiv returned a non-JSON response")
        try:
            return buffered.json()
        except ValueError as error:
            raise InvalidResponseError("alphaXiv returned invalid JSON") from error

    @staticmethod
    def _parse_model[ModelT: BaseModel](payload: object, model: type[ModelT]) -> ModelT:
        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise InvalidResponseError.from_validation_error(error) from error

    @staticmethod
    def _parse_list[ModelT: BaseModel](payload: object, model: type[ModelT]) -> list[ModelT]:
        if not isinstance(payload, list):
            raise InvalidResponseError("alphaXiv returned an invalid response")
        try:
            return [model.model_validate(item) for item in payload]
        except ValidationError as error:
            raise InvalidResponseError.from_validation_error(error) from error

    @classmethod
    def _query(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            msg = "query must not be empty"
            raise ValueError(msg)
        if len(clean) > cls.MAX_QUERY_LENGTH:
            msg = f"query must not exceed {cls.MAX_QUERY_LENGTH} characters"
            raise ValueError(msg)
        if any(ord(character) < 32 or ord(character) == 127 for character in clean):
            msg = "query must not contain control characters"
            raise ValueError(msg)
        return clean

    @classmethod
    def _topic(cls, value: str) -> str:
        clean = cls._query(value)
        if len(clean) > 100:
            msg = "topic must not exceed 100 characters"
            raise ValueError(msg)
        return clean

    @staticmethod
    def _language(value: str) -> str:
        if len(value) != 2 or not value.isascii() or not value.isalpha() or value != value.lower():
            msg = "language must be a two-letter lowercase code"
            raise ValueError(msg)
        return value

    @staticmethod
    def _bounded(value: int, *, maximum: int, name: str) -> int:
        if not 1 <= value <= maximum:
            msg = f"{name} must be between 1 and {maximum}"
            raise ValueError(msg)
        return value
