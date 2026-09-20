import json
from typing import Self

import pytest
from typer.testing import CliRunner

import axiv.commands.common as common_command
from axiv.cli import app
from axiv.errors import RateLimitError
from axiv.models.mcp import AnswerPdfQueriesArguments
from axiv.models.mcp import DiscoverPapersArguments
from axiv.models.mcp import GetPaperContentArguments
from axiv.models.mcp import GithubRepositoryArguments
from axiv.models.mcp import McpInitializeResult
from axiv.models.mcp import McpTextResult

runner = CliRunner()


class FakeMcpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.error: Exception | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.calls.append(("close", None))

    async def initialize(self) -> McpInitializeResult:
        self.calls.append(("initialize", None))
        return McpInitializeResult(protocol_version="2025-03-26", server_name="alphaXiv")

    def _result(self, tool: str, arguments: object) -> McpTextResult:
        self.calls.append((tool, arguments))
        if self.error is not None:
            raise self.error
        return McpTextResult(tool=tool, text=f"{tool} result")

    async def discover_papers(self, arguments: DiscoverPapersArguments) -> McpTextResult:
        return self._result("discover_papers", arguments)

    async def get_paper_content(self, arguments: GetPaperContentArguments) -> McpTextResult:
        return self._result("get_paper_content", arguments)

    async def answer_pdf_queries(self, arguments: AnswerPdfQueriesArguments) -> McpTextResult:
        return self._result("answer_pdf_queries", arguments)

    async def read_github_files(self, arguments: GithubRepositoryArguments) -> McpTextResult:
        return self._result("read_files_from_github_repository", arguments)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeMcpClient:
    fake = FakeMcpClient()
    monkeypatch.setattr(common_command, "McpClient", lambda: fake)
    return fake


@pytest.mark.parametrize(
    "command",
    [
        ["research", "discover"],
        ["paper", "content"],
        ["paper", "query"],
        ["paper", "code"],
    ],
)
def test_research_commands_have_offline_help(command: list[str]) -> None:
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0


def test_discover_validates_explicit_options_and_emits_json(fake_client: FakeMcpClient) -> None:
    result = runner.invoke(
        app,
        [
            "research",
            "discover",
            "How do transformers use attention?",
            "--keyword",
            "transformer",
            "--keyword",
            "attention",
            "--difficulty",
            "6",
            "--published-after",
            "2017-01-01",
            "--prioritize",
            "historical",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["tool"] == "discover_papers"
    arguments = fake_client.calls[1][1]
    assert isinstance(arguments, DiscoverPapersArguments)
    assert arguments.keywords == ("transformer", "attention")
    assert arguments.difficulty == 6
    assert arguments.published_after is not None
    assert arguments.published_after.isoformat() == "2017-01-01"
    assert [name for name, _ in fake_client.calls] == ["initialize", "discover_papers", "close"]


def test_paper_content_normalizes_arxiv_id_and_preserves_full_text(fake_client: FakeMcpClient) -> None:
    result = runner.invoke(app, ["paper", "content", "1706.03762", "--full-text", "--json"])

    assert result.exit_code == 0
    arguments = fake_client.calls[1][1]
    assert isinstance(arguments, GetPaperContentArguments)
    assert str(arguments.url) == "https://arxiv.org/abs/1706.03762"
    assert arguments.full_text is True
    assert [name for name, _ in fake_client.calls] == ["initialize", "get_paper_content", "close"]


def test_paper_query_batches_repeated_queries_in_one_call(fake_client: FakeMcpClient) -> None:
    result = runner.invoke(
        app,
        [
            "paper",
            "query",
            "1706.03762",
            "--query",
            "What datasets were used?",
            "--query",
            "What limitations are listed?",
            "--json",
        ],
    )

    assert result.exit_code == 0
    arguments = fake_client.calls[1][1]
    assert isinstance(arguments, AnswerPdfQueriesArguments)
    assert arguments.queries == ("What datasets were used?", "What limitations are listed?")
    assert [name for name, _ in fake_client.calls] == ["initialize", "answer_pdf_queries", "close"]


def test_paper_code_uses_validated_github_repository_and_path(fake_client: FakeMcpClient) -> None:
    result = runner.invoke(
        app,
        ["paper", "code", "https://github.com/owner/repo", "src/model.py", "--json"],
    )

    assert result.exit_code == 0
    arguments = fake_client.calls[1][1]
    assert isinstance(arguments, GithubRepositoryArguments)
    assert str(arguments.github_url) == "https://github.com/owner/repo"
    assert arguments.path == "src/model.py"
    assert [name for name, _ in fake_client.calls] == ["initialize", "read_files_from_github_repository", "close"]


def test_research_validation_and_quota_errors_are_stable(fake_client: FakeMcpClient) -> None:
    invalid = runner.invoke(
        app,
        ["research", "discover", "Question", "--keyword", "topic", "--difficulty", "11"],
    )
    assert invalid.exit_code == 2
    assert fake_client.calls == []

    fake_client.error = RateLimitError("Assistant quota exhausted")
    quota = runner.invoke(
        app,
        ["research", "discover", "Question", "--keyword", "topic", "--json"],
    )

    assert quota.exit_code == 5
    assert json.loads(quota.stderr)["error"]["code"] == "rate_limited"
    assert [name for name, _ in fake_client.calls] == ["initialize", "discover_papers", "close"]


def test_research_human_output_prints_complete_text(fake_client: FakeMcpClient) -> None:
    result = runner.invoke(app, ["paper", "query", "1706.03762", "--query", "Question"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "answer_pdf_queries result"
