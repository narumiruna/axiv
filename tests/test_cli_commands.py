import json
from typing import Self

import pytest
from typer.testing import CliRunner

import axiv.commands.events as events_command
import axiv.commands.feed as feed_command
import axiv.commands.paper as paper_command
import axiv.commands.researchers as researchers_command
import axiv.commands.search as search_command
from axiv.cli import app
from axiv.errors import NotFoundError
from axiv.models.events import Event
from axiv.models.events import EventsResponse
from axiv.models.feed import FeedResponse
from axiv.models.feed import TopicGroup
from axiv.models.feed import TopicGroupsResponse
from axiv.models.paper import AIDetectionResponse
from axiv.models.paper import AutoresearchImplementationsResponse
from axiv.models.paper import ExtrasResponse
from axiv.models.paper import FiguresResponse
from axiv.models.paper import FullTextResponse
from axiv.models.paper import ImplementationsResponse
from axiv.models.paper import ModelLinksResponse
from axiv.models.paper import OverviewResponse
from axiv.models.paper import OverviewStatus
from axiv.models.paper import PaperComments
from axiv.models.paper import PaperMetrics
from axiv.models.paper import PaperPage
from axiv.models.paper import PaperPreview
from axiv.models.paper import PaperRecord
from axiv.models.paper import SimilarPapers
from axiv.models.researchers import Researcher
from axiv.models.researchers import ResearchersResponse
from axiv.models.search import FullTextSearchResult
from axiv.models.search import FullTextSearchResults
from axiv.models.search import Organization
from axiv.models.search import OrganizationResults
from axiv.models.search import PaperSearchResult
from axiv.models.search import PaperSearchResults
from axiv.models.search import TopicSuggestions

runner = CliRunner()


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.closed = False
        self.record = PaperRecord(
            type="public",
            groupId="group-id",
            versionId="version-id",
            universalId="1706.03762",
            versionLabel="v1",
            versionOrder=1,
            title="Attention Is All You Need",
            abstract="An abstract.",
        )
        self.preview = PaperPreview(
            id="group-id",
            paper_group_id="group-id",
            version_id="version-id",
            universal_paper_id="1706.03762",
            title="Attention Is All You Need",
            abstract="An abstract.",
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.closed = True

    def search_papers(self, query: str) -> PaperSearchResults:
        self.calls.append(("search_papers", query))
        items = [PaperSearchResult(paperId="1706.03762", title="Attention", snippet="A snippet")]
        return PaperSearchResults(items=items, count=1)

    def search_full_text(self, query: str, *, limit: int) -> FullTextSearchResults:
        self.calls.append(("search_full_text", (query, limit)))
        items = [FullTextSearchResult(paperId="1706.03762", title="Attention", abstract="Abstract")]
        return FullTextSearchResults(items=items, count=1)

    def closest_topics(self, query: str) -> TopicSuggestions:
        self.calls.append(("closest_topics", query))
        return TopicSuggestions(data=["transformers"])

    def search_organizations(self, query: str) -> OrganizationResults:
        self.calls.append(("search_organizations", query))
        items = [Organization(id="org-id", name="MIT", slug="mit")]
        return OrganizationResults(items=items, count=1)

    def list_researchers(self, *, offset: int | None = None) -> ResearchersResponse:
        self.calls.append(("list_researchers", offset))
        return ResearchersResponse(researchers=[Researcher(slug="reader", name="Reader")])

    def search_researchers(self, query: str) -> ResearchersResponse:
        self.calls.append(("search_researchers", query))
        return ResearchersResponse(researchers=[Researcher(slug="reader", name="Reader")])

    def list_events(self) -> EventsResponse:
        self.calls.append(("list_events", None))
        event = Event(
            id="event-id",
            title="Research Talk",
            organization="MIT",
            link="https://example.com",
            date="2026-08-13",
        )
        return EventsResponse(items=[event], count=1)

    def feed(self, **kwargs: object) -> FeedResponse:
        self.calls.append(("feed", kwargs))
        return FeedResponse(page=0, papers=[self.preview])

    def icml_topics(self) -> TopicGroupsResponse:
        self.calls.append(("icml_topics", None))
        return TopicGroupsResponse(topicGroups=[TopicGroup(group="Deep Learning", count=1, subtopics=[])])

    def paper(self, identifier: str) -> PaperRecord:
        self.calls.append(("paper", identifier))
        return self.record

    def paper_preview(self, identifier: str) -> PaperPreview:
        self.calls.append(("paper_preview", identifier))
        return self.preview

    def paper_full_text(self, version_id: str) -> FullTextResponse:
        self.calls.append(("paper_full_text", version_id))
        return FullTextResponse(pages=[PaperPage(pageNumber=1, text="Page one")])

    def paper_overview(self, version_id: str, language: str) -> OverviewResponse:
        self.calls.append(("paper_overview", (version_id, language)))
        return OverviewResponse(title="Attention", abstract="Abstract", overview="Overview")

    def paper_overview_status(self, version_id: str) -> OverviewStatus:
        self.calls.append(("paper_overview_status", version_id))
        return OverviewStatus(state="done", updatedAt=1, translations={})

    def paper_comments(self, group_id: str) -> PaperComments:
        self.calls.append(("paper_comments", group_id))
        return PaperComments(items=[], count=0)

    def similar_papers(self, identifier: str, *, limit: int) -> SimilarPapers:
        self.calls.append(("similar_papers", (identifier, limit)))
        return SimilarPapers(items=[self.preview], count=1)

    def paper_metrics(self, identifier: str) -> PaperMetrics:
        self.calls.append(("paper_metrics", identifier))
        return PaperMetrics(commentsCount=1, publicTotalVotes=2, visitsAll=3)

    def paper_figures(self, group_id: str) -> FiguresResponse:
        self.calls.append(("paper_figures", group_id))
        return FiguresResponse(figures=["figure.png"])

    def paper_extras(self, group_id: str) -> ExtrasResponse:
        self.calls.append(("paper_extras", group_id))
        return ExtrasResponse(links=[], repoUrl=None, autoresearch=False, featuredTweets=None)

    def paper_implementations(self, group_id: str) -> ImplementationsResponse:
        self.calls.append(("paper_implementations", group_id))
        return ImplementationsResponse(alphaXivImplementations=[], paperResources=[])

    def autoresearch_implementations(self, group_id: str) -> AutoresearchImplementationsResponse:
        self.calls.append(("autoresearch_implementations", group_id))
        return AutoresearchImplementationsResponse(implementations=[])

    def ai_detection(self, version_id: str) -> AIDetectionResponse:
        self.calls.append(("ai_detection", version_id))
        return AIDetectionResponse(
            state="done",
            fractionAi=0,
            fractionAiAssisted=0,
            fractionHuman=1,
            predictionShort="Human",
            windows=[],
            updatedAt=1,
        )

    def model_links(self, version_id: str) -> ModelLinksResponse:
        self.calls.append(("model_links", version_id))
        return ModelLinksResponse(state="done", matches=[], updatedAt=1, isOutdated=False)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    fake = FakeClient()
    for module in (search_command, researchers_command, events_command, feed_command, paper_command):
        monkeypatch.setattr(module, "PublicRestClient", lambda: fake, raising=False)
    return fake


@pytest.mark.parametrize(
    "command",
    [
        ["search", "papers"],
        ["search", "full-text"],
        ["search", "topics"],
        ["search", "organizations"],
        ["researchers", "list"],
        ["researchers", "search"],
        ["events", "list"],
        ["feed", "list"],
        ["feed", "topics"],
        ["paper", "show"],
        ["paper", "preview"],
        ["paper", "text"],
        ["paper", "overview"],
        ["paper", "related"],
    ],
)
def test_each_static_command_has_help(command: list[str]) -> None:
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0


def test_search_papers_json_is_stable_and_human_output_is_readable(fake_client: FakeClient) -> None:
    json_result = runner.invoke(app, ["search", "papers", "transformer", "--json"])
    human_result = runner.invoke(app, ["search", "papers", "transformer"])

    assert json_result.exit_code == 0
    assert json.loads(json_result.stdout)["items"][0]["paper_id"] == "1706.03762"
    assert human_result.exit_code == 0
    assert "Attention" in human_result.stdout
    assert fake_client.calls == [("search_papers", "transformer"), ("search_papers", "transformer")]


@pytest.mark.parametrize(
    ("args", "expected_call"),
    [
        (["search", "full-text", "query", "--limit", "3", "--json"], "search_full_text"),
        (["search", "topics", "query", "--json"], "closest_topics"),
        (["search", "organizations", "query", "--json"], "search_organizations"),
        (["researchers", "list", "--json"], "list_researchers"),
        (["researchers", "search", "query", "--json"], "search_researchers"),
        (["events", "list", "--json"], "list_events"),
        (["feed", "list", "--limit", "3", "--json"], "feed"),
        (["feed", "topics", "--json"], "icml_topics"),
        (["paper", "show", "1706.03762", "--json"], "paper"),
        (["paper", "preview", "1706.03762", "--json"], "paper_preview"),
        (["paper", "text", "1706.03762", "--json"], "paper_full_text"),
        (["paper", "overview", "1706.03762", "--json"], "paper_overview"),
    ],
)
def test_read_commands_return_json_and_call_fixed_client_method(
    args: list[str],
    expected_call: str,
    fake_client: FakeClient,
) -> None:
    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert json.loads(result.stdout)
    assert expected_call in [call[0] for call in fake_client.calls]


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize(
    ("kind", "method", "argument", "payload", "summary"),
    [
        ("comments", "paper_comments", "group-id", {"items": [], "count": 0}, "0 items"),
        ("similar", "similar_papers", ("1706.03762", 3), None, "1 items"),
        (
            "metrics",
            "paper_metrics",
            "1706.03762",
            {"comments_count": 1, "public_total_votes": 2, "visits_all": 3},
            "3 visits, 1 comments",
        ),
        ("figures", "paper_figures", "group-id", {"figures": ["figure.png"]}, "1 figures"),
        (
            "extras",
            "paper_extras",
            "group-id",
            {"links": [], "repo_url": None, "autoresearch": False, "featured_tweets": None},
            "No repository",
        ),
        (
            "implementations",
            "paper_implementations",
            "group-id",
            {"alphaxiv_implementations": [], "paper_resources": []},
            "0 implementations",
        ),
        ("autoresearch", "autoresearch_implementations", "group-id", {"implementations": []}, "0 implementations"),
        (
            "ai-detection",
            "ai_detection",
            "version-id",
            {
                "state": "done",
                "fraction_ai": 0,
                "fraction_ai_assisted": 0,
                "fraction_human": 1,
                "prediction_short": "Human",
                "headline": None,
                "windows": [],
                "updated_at": 1,
            },
            "done: No headline",
        ),
        (
            "model-links",
            "model_links",
            "version-id",
            {"state": "done", "matches": [], "updated_at": 1, "is_outdated": False},
            "done: 0 matches",
        ),
    ],
)
def test_related_kind_dispatches_only_to_static_methods(
    kind, method, argument, payload, summary, json_output, fake_client
):
    flags = ["--json"] if json_output else []
    result = runner.invoke(app, ["paper", "related", "1706.03762", "--kind", kind, "--limit", "3", *flags])

    assert result.exit_code == 0
    assert result.stderr == ""
    lookup = [] if kind in {"similar", "metrics"} else [("paper", "1706.03762")]
    assert fake_client.calls == [*lookup, (method, argument)]
    assert fake_client.closed is True
    if json_output:
        expected = (
            {"items": [fake_client.preview.model_dump(mode="json")], "count": 1} if kind == "similar" else payload
        )
        assert json.loads(result.stdout) == expected
    else:
        assert "Related paper data" in result.stdout
        assert kind in result.stdout
        assert summary in result.stdout
        assert len(result.stdout) < 1_000


def test_related_human_output_is_bounded_summary(fake_client: FakeClient) -> None:
    result = runner.invoke(app, ["paper", "related", "1706.03762", "--kind", "metrics"])

    assert result.exit_code == 0
    assert "3 visits, 1 comments" in result.stdout
    assert len(result.stdout) < 1_000


@pytest.mark.parametrize(
    ("args", "method"),
    [
        (["search", "papers", "query"], "search_papers"),
        (["search", "organizations", "query"], "search_organizations"),
        (["events", "list"], "list_events"),
    ],
)
def test_client_side_limit_preserves_items_and_recalculates_count(args, method, fake_client, monkeypatch):
    original = getattr(fake_client, method)

    def many(*arguments):
        result = original(*arguments)
        return type(result)(items=result.items * 3, count=3)

    monkeypatch.setattr(fake_client, method, many)
    result = runner.invoke(app, [*args, "--limit", "2", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["items"]) == payload["count"] == 2
    assert len(fake_client.calls) == 1


def test_limits_are_rejected_before_client_call(fake_client: FakeClient) -> None:
    result = runner.invoke(app, ["feed", "list", "--limit", "51"])

    assert result.exit_code == 2
    assert fake_client.calls == []


def test_domain_error_uses_stderr_and_stable_exit_code(
    fake_client: FakeClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_query: str) -> PaperSearchResults:
        raise NotFoundError("paper not found")

    monkeypatch.setattr(fake_client, "search_papers", fail)

    result = runner.invoke(app, ["search", "papers", "missing", "--json"])

    assert result.exit_code == 4
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "not_found"
    assert "Traceback" not in result.stderr


def test_unexpected_error_does_not_disclose_details_without_debug(
    fake_client: FakeClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_query: str) -> PaperSearchResults:
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr(fake_client, "search_papers", fail)

    result = runner.invoke(app, ["search", "papers", "query"])

    assert result.exit_code == 6
    assert "private implementation detail" not in result.stderr
    assert "unexpected axiv CLI error" in result.stderr


def test_text_human_output_defaults_to_one_page(fake_client: FakeClient) -> None:
    result = runner.invoke(app, ["paper", "text", "1706.03762"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Page one"


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize(
    ("args", "call", "payload", "human"),
    [
        (
            ["text"],
            ("paper_full_text", "version-id"),
            {"pages": [{"page_number": 1, "text": "Page one"}]},
            "Page one",
        ),
        (
            ["overview"],
            ("paper_overview", ("version-id", "en")),
            {
                "title": "Attention",
                "abstract": "Abstract",
                "summary": None,
                "overview": "Overview",
                "intermediate_report": None,
                "citations": [],
                "summary_section_titles": {},
                "overview_section_titles": {},
            },
            "Overview",
        ),
        (
            ["overview", "--status"],
            ("paper_overview_status", "version-id"),
            {"state": "done", "updated_at": 1, "translations": {}},
            None,
        ),
    ],
)
def test_text_and_overview_preserve_routing_and_output(args, call, payload, human, json_output, fake_client):
    flags = ["--json"] if json_output else []
    result = runner.invoke(app, ["paper", *args, "1706.03762", *flags])

    assert result.exit_code == 0
    assert result.stderr == ""
    assert fake_client.calls == [("paper", "1706.03762"), call]
    assert fake_client.closed is True
    if json_output or human is None:
        assert json.loads(result.stdout) == payload
    else:
        assert result.stdout == f"{human}\n"


def test_overview_passes_language_with_resolved_version(fake_client):
    result = runner.invoke(app, ["paper", "overview", "1706.03762", "--language", "fr", "--json"])

    assert result.exit_code == 0
    assert fake_client.calls == [("paper", "1706.03762"), ("paper_overview", ("version-id", "fr"))]


@pytest.mark.parametrize("json_output", [False, True])
def test_text_missing_page_preserves_error_in_both_output_modes(fake_client, json_output):
    flags = ["--json"] if json_output else []
    result = runner.invoke(app, ["paper", "text", "1706.03762", "--page", "2", *flags])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert json.loads(result.stderr) == {
        "error": {"code": "invalid_input", "message": "paper text does not contain page 2"}
    }
    assert fake_client.calls == [("paper", "1706.03762"), ("paper_full_text", "version-id")]
    assert fake_client.closed is True


@pytest.mark.parametrize("json_output", [False, True])
def test_text_selects_requested_page_only_in_human_mode(fake_client, monkeypatch, json_output):
    pages = [{"pageNumber": 1, "text": "Page one"}, {"pageNumber": 3, "text": "Page three"}]

    def full_text(version_id):
        fake_client.calls.append(("paper_full_text", version_id))
        return FullTextResponse.model_validate({"pages": pages})

    monkeypatch.setattr(fake_client, "paper_full_text", full_text)
    flags = ["--json"] if json_output else []
    result = runner.invoke(app, ["paper", "text", "1706.03762", "--page", "3", *flags])

    assert result.exit_code == 0
    assert result.stderr == ""
    if json_output:
        assert json.loads(result.stdout) == {
            "pages": [{"page_number": 1, "text": "Page one"}, {"page_number": 3, "text": "Page three"}]
        }
    else:
        assert result.stdout == "Page three\n"
    assert fake_client.calls == [("paper", "1706.03762"), ("paper_full_text", "version-id")]
    assert fake_client.closed is True


@pytest.mark.parametrize("args", [["text"], ["overview"], ["related", "--kind", "figures"]])
def test_failed_paper_lookup_stops_before_dependent_request(fake_client, monkeypatch, args):
    def fail(identifier):
        fake_client.calls.append(("paper", identifier))
        raise NotFoundError("paper not found")

    monkeypatch.setattr(fake_client, "paper", fail)
    result = runner.invoke(app, ["paper", *args, "missing", "--json"])

    assert result.exit_code == 4
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"error": {"code": "not_found", "message": "paper not found"}}
    assert fake_client.calls == [("paper", "missing")]
    assert fake_client.closed is True
