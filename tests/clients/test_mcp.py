from types import SimpleNamespace

import anyio
import pytest

import axiv.clients.mcp as mcp_client_module
from axiv.clients.mcp import McpClient
from axiv.errors import InputError
from axiv.errors import PermissionDeniedError
from axiv.errors import RateLimitError
from axiv.errors import RemoteAPIError
from axiv.models.mcp import AnswerPdfQueriesArguments
from axiv.models.mcp import CreateFolderArguments
from axiv.models.mcp import DeleteFolderArguments
from axiv.models.mcp import DiscoverPapersArguments
from axiv.models.mcp import GetPaperContentArguments
from axiv.models.mcp import GithubRepositoryArguments
from axiv.models.mcp import ListLibraryArguments
from axiv.models.mcp import MovePapersArguments
from axiv.models.mcp import RemovePapersArguments
from axiv.models.mcp import RenameFolderArguments
from axiv.models.mcp import SavePapersArguments


class FakeStreamContext:
    def __init__(self) -> None:
        self.closed = False

    async def __aenter__(self) -> tuple[object, object, None]:
        return object(), object(), None

    async def __aexit__(self, *_args: object) -> None:
        self.closed = True


class FakeSession:
    def __init__(self) -> None:
        self.closed = False
        self.initialize_calls = 0
        self.call_result: object = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="first"), SimpleNamespace(type="text", text="second")],
            isError=False,
            structuredContent={"requestId": "request-1"},
        )
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.results_by_tool: dict[str, object] = {}

    async def initialize(self) -> object:
        self.initialize_calls += 1
        return SimpleNamespace(
            protocolVersion="2025-03-26",
            serverInfo=SimpleNamespace(name="alphaXiv", version="1.0"),
        )

    async def list_tools(self) -> object:
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="discover_papers",
                    description="Discover papers",
                    inputSchema={
                        "type": "object",
                        "properties": {"question": {"type": "string"}},
                        "required": ["question"],
                    },
                )
            ]
        )

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        self.calls.append((name, arguments))
        return self.results_by_tool.get(name, self.call_result)


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        self.session.closed = True


def make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session: FakeSession | None = None,
) -> tuple[McpClient, FakeStreamContext, FakeSession, list[tuple[str, dict[str, str]]]]:
    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-test-secret")
    stream_context = FakeStreamContext()
    fake_session = session or FakeSession()
    stream_calls: list[tuple[str, dict[str, str]]] = []

    def stream_factory(url: str, *, headers: dict[str, str]) -> FakeStreamContext:
        stream_calls.append((url, headers))
        return stream_context

    def session_factory(_read: object, _write: object) -> FakeSessionContext:
        return FakeSessionContext(fake_session)

    client = McpClient(_stream_factory=stream_factory, _session_factory=session_factory)
    return client, stream_context, fake_session, stream_calls


def test_missing_api_key_is_rejected_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPHAXIV_API_KEY", raising=False)

    with pytest.raises(InputError, match="ALPHAXIV_API_KEY"):
        McpClient()


def test_fixed_endpoint_bearer_header_and_initialize_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stream, session, stream_calls = make_client(monkeypatch)

    async def scenario() -> None:
        async with client:
            result = await client.initialize()
            assert result.protocol_version == "2025-03-26"
            assert result.server_name == "alphaXiv"

    anyio.run(scenario)

    assert stream_calls == [
        (
            "https://api.alphaxiv.org/mcp/v1",
            {"Authorization": "Bearer axv-test-secret"},
        )
    ]
    assert session.initialize_calls == 1
    assert session.closed is True
    assert stream.closed is True


def test_list_tools_returns_typed_names_and_required_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _, _ = make_client(monkeypatch)

    async def scenario() -> None:
        async with client:
            await client.initialize()
            result = await client.list_tools()
        assert result.tools[0].name == "discover_papers"
        assert result.tools[0].required_arguments == ("question",)

    anyio.run(scenario)


def test_tool_text_content_is_combined_without_losing_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, session, _ = make_client(monkeypatch)
    arguments = DiscoverPapersArguments(
        question="Which papers explain attention?",
        keywords=("attention",),
        difficulty=5,
    )

    async def scenario() -> None:
        async with client:
            await client.initialize()
            result = await client.discover_papers(arguments)
        assert result.text == "first\nsecond"
        assert result.is_error is False
        assert result.metadata == {"requestId": "request-1"}

    anyio.run(scenario)

    assert session.calls == [
        (
            "discover_papers",
            {
                "keywords": ["attention"],
                "question": "Which papers explain attention?",
                "difficulty": 5.0,
            },
        )
    ]


def test_each_public_method_dispatches_one_fixed_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, session, _ = make_client(monkeypatch)
    session.results_by_tool["list_library"] = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"folders": []}')],
        isError=False,
        structuredContent=None,
    )
    mutation_result = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"count": 1}')],
        isError=False,
        structuredContent=None,
    )
    for tool in (
        "save_papers_to_folder",
        "remove_papers_from_folder",
        "move_papers_between_folders",
        "create_folder",
        "rename_folder",
        "delete_folder",
    ):
        session.results_by_tool[tool] = mutation_result

    async def scenario() -> None:
        async with client:
            await client.initialize()
            await client.discover_papers(
                DiscoverPapersArguments(keywords=("attention",), question="Question", difficulty=3)
            )
            await client.get_paper_content(GetPaperContentArguments(url="https://arxiv.org/abs/1706.03762"))
            await client.answer_pdf_queries(
                AnswerPdfQueriesArguments(paper="1706.03762", queries=("What is the method?",))
            )
            await client.read_github_files(
                GithubRepositoryArguments(githubUrl="https://github.com/owner/repo", path="/")
            )
            await client.list_library(ListLibraryArguments())
            await client.save_papers(SavePapersArguments(folder_id="folder-1", paper_ids_or_urls=("1706.03762",)))
            await client.remove_papers(RemovePapersArguments(folder_id="folder-1", paper_ids_or_urls=("1706.03762",)))
            await client.move_papers(
                MovePapersArguments(
                    from_folder_id="folder-1",
                    to_folder_id="folder-2",
                    paper_ids_or_urls=("1706.03762",),
                )
            )
            await client.create_folder(CreateFolderArguments(name="Reading"))
            await client.rename_folder(RenameFolderArguments(folder_id="folder-1", name="Read next"))
            await client.delete_folder(DeleteFolderArguments(folder_id="folder-1"))

    anyio.run(scenario)

    assert [name for name, _ in session.calls] == [
        "discover_papers",
        "get_paper_content",
        "answer_pdf_queries",
        "read_files_from_github_repository",
        "list_library",
        "save_papers_to_folder",
        "remove_papers_from_folder",
        "move_papers_between_folders",
        "create_folder",
        "rename_folder",
        "delete_folder",
    ]


def test_tool_error_is_mapped_without_disclosing_structured_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    session.call_result = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Quota exhausted\x1b[31m")],
        isError=True,
        structuredContent={"apiKey": "axv-private"},
    )
    client, _, _, _ = make_client(monkeypatch, session=session)

    async def scenario() -> None:
        async with client:
            await client.initialize()
            with pytest.raises(RemoteAPIError, match="Quota exhausted") as captured:
                await client.discover_papers(
                    DiscoverPapersArguments(keywords=("topic",), question="Question", difficulty=1)
                )
            assert "axv-private" not in str(captured.value)
            assert "\x1b" not in str(captured.value)

    anyio.run(scenario)


def test_session_and_stream_close_when_initialization_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingSession(FakeSession):
        async def initialize(self) -> object:
            raise RuntimeError("private protocol detail")

    session = FailingSession()
    client, stream, fake_session, _ = make_client(monkeypatch, session=session)

    async def scenario() -> None:
        with pytest.raises(RemoteAPIError, match="MCP initialization failed") as captured:
            async with client:
                await client.initialize()
        assert "private protocol detail" not in str(captured.value)

    anyio.run(scenario)

    assert fake_session.closed is True
    assert stream.closed is True


def test_production_streamable_sends_auth_without_head_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeHttpClient:
        def __init__(self) -> None:
            self.closed = False

        async def __aenter__(self) -> "FakeHttpClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            self.closed = True

    fake_http = FakeHttpClient()
    fake_transport = FakeStreamContext()
    captured_headers: list[dict[str, str]] = []

    def http_factory(*, headers: dict[str, str]) -> FakeHttpClient:
        captured_headers.append(headers)
        return fake_http

    def stream_factory(url: str, *, http_client: object) -> FakeStreamContext:
        assert url == "https://api.alphaxiv.org/mcp/v1"
        assert http_client is fake_http
        return fake_transport

    monkeypatch.setattr(mcp_client_module, "create_mcp_http_client", http_factory)
    monkeypatch.setattr(mcp_client_module, "streamable_http_client", stream_factory)

    async def scenario() -> None:
        async with mcp_client_module._production_streamable(
            "https://api.alphaxiv.org/mcp/v1",
            headers={"Authorization": "Bearer axv-test-secret"},
        ) as streams:
            assert len(streams) == 3

    anyio.run(scenario)

    assert captured_headers == [{"Authorization": "Bearer axv-test-secret"}]
    assert fake_transport.closed is True
    assert fake_http.closed is True


def test_production_sse_sends_auth_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sse = FakeStreamContext()
    captured_headers: list[dict[str, str]] = []

    def sse_factory(url: str, *, headers: dict[str, str]) -> FakeStreamContext:
        assert url == "https://api.alphaxiv.org/mcp/v1"
        captured_headers.append(headers)
        return fake_sse

    monkeypatch.setattr(mcp_client_module, "sse_client", sse_factory)

    async def scenario() -> None:
        async with mcp_client_module._production_sse(
            "https://api.alphaxiv.org/mcp/v1",
            headers={"Authorization": "Bearer axv-test-secret"},
        ) as streams:
            assert len(streams) == 3

    anyio.run(scenario)

    assert captured_headers == [{"Authorization": "Bearer axv-test-secret"}]
    assert fake_sse.closed is True


def test_connection_failure_falls_back_before_initialization(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingStreamContext(FakeStreamContext):
        async def __aenter__(self) -> tuple[object, object, None]:
            raise RuntimeError("streamable unavailable")

    primary_stream = FailingStreamContext()
    fallback_stream = FakeStreamContext()
    fallback_session = FakeSession()
    fallback_calls = 0

    def primary_factory(_url: str, *, headers: dict[str, str]) -> FailingStreamContext:
        assert headers["Authorization"] == "Bearer axv-test-secret"
        return primary_stream

    def fallback_factory(_url: str, *, headers: dict[str, str]) -> FakeStreamContext:
        nonlocal fallback_calls
        assert headers["Authorization"] == "Bearer axv-test-secret"
        fallback_calls += 1
        return fallback_stream

    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-test-secret")
    client = McpClient(
        _stream_factory=primary_factory,
        _fallback_stream_factory=fallback_factory,
        _session_factory=lambda _read, _write: FakeSessionContext(fallback_session),
    )

    async def scenario() -> None:
        async with client:
            initialized = await client.initialize()
            assert initialized.server_name == "alphaXiv"

    anyio.run(scenario)

    assert fallback_calls == 1
    assert fallback_stream.closed is True
    assert fallback_session.closed is True


def test_initialization_failure_replaces_primary_session_once(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingSession(FakeSession):
        async def initialize(self) -> object:
            self.initialize_calls += 1
            raise RuntimeError("streamable initialize failed")

    class NamedStreamContext(FakeStreamContext):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

        async def __aenter__(self) -> tuple[str, object, None]:
            return self.name, object(), None

    class NoisySessionContext(FakeSessionContext):
        async def __aexit__(self, *_args: object) -> None:
            await super().__aexit__(*_args)
            raise RuntimeError("primary cleanup failed")

    primary_stream = NamedStreamContext("primary")
    fallback_stream = NamedStreamContext("fallback")
    primary_session = FailingSession()
    fallback_session = FakeSession()
    fallback_calls = 0

    def fallback_factory(_url: str, *, headers: dict[str, str]) -> NamedStreamContext:
        nonlocal fallback_calls
        fallback_calls += 1
        return fallback_stream

    def session_factory(read: object, _write: object) -> FakeSessionContext:
        if read == "primary":
            return NoisySessionContext(primary_session)
        return FakeSessionContext(fallback_session)

    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-test-secret")
    client = McpClient(
        _stream_factory=lambda _url, headers: primary_stream,
        _fallback_stream_factory=fallback_factory,
        _session_factory=session_factory,
    )

    async def scenario() -> None:
        async with client:
            initialized = await client.initialize()
            await client.discover_papers(
                DiscoverPapersArguments(keywords=("agents",), question="Question", difficulty=3)
            )
            assert initialized.server_name == "alphaXiv"

    anyio.run(scenario)

    assert primary_session.initialize_calls == 1
    assert primary_session.closed is True
    assert primary_stream.closed is True
    assert fallback_session.initialize_calls == 1
    assert [name for name, _ in fallback_session.calls] == ["discover_papers"]
    assert fallback_calls == 1


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [(403, PermissionDeniedError), (429, RateLimitError)],
)
def test_authentication_and_rate_limit_failures_do_not_fallback(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    error_type: type[Exception],
) -> None:
    class StatusError(Exception):
        def __init__(self, status: int) -> None:
            self.response = SimpleNamespace(status_code=status)
            super().__init__(f"private status {status}")

    class FailingSession(FakeSession):
        async def initialize(self) -> object:
            raise StatusError(status_code)

    fallback_calls = 0

    def fallback_factory(_url: str, *, headers: dict[str, str]) -> FakeStreamContext:
        nonlocal fallback_calls
        fallback_calls += 1
        return FakeStreamContext()

    primary_stream = FakeStreamContext()
    failing_session = FailingSession()
    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-test-secret")
    client = McpClient(
        _stream_factory=lambda _url, headers: primary_stream,
        _fallback_stream_factory=fallback_factory,
        _session_factory=lambda _read, _write: FakeSessionContext(failing_session),
    )

    async def scenario() -> None:
        async with client:
            with pytest.raises(error_type):
                await client.initialize()

    anyio.run(scenario)

    assert fallback_calls == 0


def test_fallback_initialization_failure_is_terminal_and_closes_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingSession(FakeSession):
        async def initialize(self) -> object:
            self.initialize_calls += 1
            raise RuntimeError("initialization failed")

    streams = [FakeStreamContext(), FakeStreamContext()]
    sessions = [FailingSession(), FailingSession()]
    session_contexts = iter(FakeSessionContext(session) for session in sessions)
    fallback_calls = []

    def fallback_factory(_url: str, *, headers: dict[str, str]) -> FakeStreamContext:
        fallback_calls.append(headers)
        return streams[1]

    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-test-secret")
    client = McpClient(
        _stream_factory=lambda _url, headers: streams[0],
        _fallback_stream_factory=fallback_factory,
        _session_factory=lambda _read, _write: next(session_contexts),
    )

    async def scenario() -> None:
        with pytest.raises(RemoteAPIError, match="MCP initialization failed"):
            async with client:
                await client.initialize()

    anyio.run(scenario)

    assert len(fallback_calls) == 1
    assert all(session.initialize_calls == 1 and session.closed for session in sessions)
    assert all(stream.closed for stream in streams)
    assert all(session.calls == [] for session in sessions)


def test_tool_failure_is_not_retried_on_fallback_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingCallSession(FakeSession):
        async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
            self.calls.append((name, arguments))
            raise RuntimeError("response interrupted")

    session = FailingCallSession()
    fallback_calls = 0

    def fallback_factory(_url: str, *, headers: dict[str, str]) -> FakeStreamContext:
        nonlocal fallback_calls
        fallback_calls += 1
        return FakeStreamContext()

    primary_stream = FakeStreamContext()
    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-test-secret")
    client = McpClient(
        _stream_factory=lambda _url, headers: primary_stream,
        _fallback_stream_factory=fallback_factory,
        _session_factory=lambda _read, _write: FakeSessionContext(session),
    )

    async def scenario() -> None:
        async with client:
            await client.initialize()
            with pytest.raises(RemoteAPIError, match="MCP tool discover_papers failed"):
                await client.discover_papers(
                    DiscoverPapersArguments(keywords=("agents",), question="Question", difficulty=3)
                )

    anyio.run(scenario)

    assert len(session.calls) == 1
    assert fallback_calls == 0


def test_transport_authentication_failure_is_mapped_and_client_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-test-secret")

    class AuthenticationError(Exception):
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=401)
            super().__init__("remote detail with axv-test-secret")

    class FailingStreamContext(FakeStreamContext):
        async def __aenter__(self) -> tuple[object, object, None]:
            raise AuthenticationError

    fallback_calls = 0

    def stream_factory(_url: str, *, headers: dict[str, str]) -> FailingStreamContext:
        assert headers["Authorization"] == "Bearer axv-test-secret"
        return FailingStreamContext()

    def fallback_factory(_url: str, *, headers: dict[str, str]) -> FakeStreamContext:
        nonlocal fallback_calls
        fallback_calls += 1
        return FakeStreamContext()

    client = McpClient(_stream_factory=stream_factory, _fallback_stream_factory=fallback_factory)

    async def scenario() -> None:
        with pytest.raises(PermissionDeniedError, match="MCP authentication failed") as captured:
            async with client:
                pass
        assert "axv-test-secret" not in str(captured.value)
        with pytest.raises(RuntimeError, match="cannot be reused"):
            async with client:
                pass

    anyio.run(scenario)

    assert fallback_calls == 0


def test_authentication_status_is_mapped_without_remote_details(monkeypatch: pytest.MonkeyPatch) -> None:
    class AuthenticationError(Exception):
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=403)
            super().__init__("remote detail with axv-private")

    class FailingSession(FakeSession):
        async def initialize(self) -> object:
            raise AuthenticationError

    client, _, _, _ = make_client(monkeypatch, session=FailingSession())

    async def scenario() -> None:
        async with client:
            with pytest.raises(PermissionDeniedError, match="MCP authentication failed") as captured:
                await client.initialize()
            assert "axv-private" not in str(captured.value)

    anyio.run(scenario)


def test_plain_text_mutation_result_is_reported_without_retry_risk(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, session, _ = make_client(monkeypatch)
    session.results_by_tool["create_folder"] = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Folder created")],
        isError=False,
        structuredContent=None,
    )

    async def scenario() -> None:
        async with client:
            await client.initialize()
            result = await client.create_folder(CreateFolderArguments(name="Reading"))
        assert result.success is True
        assert result.message == "Folder created"
        assert result.details == {}

    anyio.run(scenario)


@pytest.mark.parametrize(
    "sensitive_key",
    ["apiKey", "access_token", "client-secret", "sessionCookie", "Authorization"],
)
def test_nested_sensitive_text_metadata_is_removed(
    monkeypatch: pytest.MonkeyPatch,
    sensitive_key: str,
) -> None:
    client, _, session, _ = make_client(monkeypatch)
    session.call_result = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="result")],
        isError=False,
        structuredContent={"requestId": {sensitive_key: "axv-private", "id": "request-1"}},
    )

    async def scenario() -> None:
        async with client:
            await client.initialize()
            result = await client.discover_papers(
                DiscoverPapersArguments(keywords=("topic",), question="Question", difficulty=1)
            )
        assert "axv-private" not in result.model_dump_json()
        assert result.metadata == {"requestId": {"id": "request-1"}}

    anyio.run(scenario)


@pytest.mark.parametrize(
    "sensitive_key",
    ["apiKey", "access_token", "client-secret", "sessionCookie", "Authorization"],
)
def test_nested_sensitive_mutation_details_are_removed(
    monkeypatch: pytest.MonkeyPatch,
    sensitive_key: str,
) -> None:
    client, _, session, _ = make_client(monkeypatch)
    session.results_by_tool["create_folder"] = SimpleNamespace(
        content=[],
        isError=False,
        structuredContent={"count": 1, "data": [{sensitive_key: "axv-private", "folder_id": "folder-1"}]},
    )

    async def scenario() -> None:
        async with client:
            await client.initialize()
            result = await client.create_folder(CreateFolderArguments(name="Reading"))
        assert "axv-private" not in result.model_dump_json()
        assert result.details == {"count": 1, "data": [{"folder_id": "folder-1"}]}

    anyio.run(scenario)


def test_tool_calls_require_successful_initialize(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, session, _ = make_client(monkeypatch)

    async def scenario() -> None:
        async with client:
            with pytest.raises(RuntimeError, match="initialize"):
                await client.list_tools()
        assert session.initialize_calls == 0

    anyio.run(scenario)


def test_client_cannot_be_used_outside_managed_session_or_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _, _ = make_client(monkeypatch)

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="managed session"):
            await client.list_tools()
        async with client:
            await client.initialize()
        with pytest.raises(RuntimeError, match="cannot be reused"):
            async with client:
                pass

    anyio.run(scenario)
