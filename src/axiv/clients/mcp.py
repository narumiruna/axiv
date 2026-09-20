import json
import os
from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from contextlib import AsyncExitStack
from contextlib import asynccontextmanager
from contextlib import suppress
from types import TracebackType
from typing import Any
from typing import Protocol
from typing import TypeGuard
from typing import cast

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import create_mcp_http_client
from mcp.client.streamable_http import streamable_http_client
from pydantic import JsonValue
from pydantic import ValidationError

from axiv.contracts.mcp import MCP_ENDPOINT
from axiv.contracts.mcp import MCP_TOOLS
from axiv.contracts.mcp import McpToolContract
from axiv.contracts.mcp import McpToolName
from axiv.errors import AlphaXivError
from axiv.errors import InputError
from axiv.errors import InvalidResponseError
from axiv.errors import PermissionDeniedError
from axiv.errors import RateLimitError
from axiv.errors import RemoteAPIError
from axiv.models.library import ExternalLibraryResponse
from axiv.models.library import LibraryListResult
from axiv.models.library import LibraryMutationResult
from axiv.models.mcp import AnswerPdfQueriesArguments
from axiv.models.mcp import CreateFolderArguments
from axiv.models.mcp import DeleteFolderArguments
from axiv.models.mcp import DiscoverPapersArguments
from axiv.models.mcp import GetPaperContentArguments
from axiv.models.mcp import GithubRepositoryArguments
from axiv.models.mcp import ListLibraryArguments
from axiv.models.mcp import McpArguments
from axiv.models.mcp import McpInitializeResult
from axiv.models.mcp import McpTextResult
from axiv.models.mcp import McpToolDescription
from axiv.models.mcp import McpToolList
from axiv.models.mcp import MovePapersArguments
from axiv.models.mcp import RemovePapersArguments
from axiv.models.mcp import RenameFolderArguments
from axiv.models.mcp import SavePapersArguments
from axiv.sensitive import is_sensitive_key


class Session(Protocol):
    async def initialize(self) -> object: ...

    async def list_tools(self) -> object: ...

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object: ...


StreamFactory = Callable[..., AbstractAsyncContextManager[tuple[object, ...]]]
SessionFactory = Callable[[object, object], AbstractAsyncContextManager[Session]]


def _production_session(read_stream: object, write_stream: object) -> AbstractAsyncContextManager[Session]:
    session = ClientSession(cast(Any, read_stream), cast(Any, write_stream))
    return cast(AbstractAsyncContextManager[Session], session)


@asynccontextmanager
async def _production_streamable(url: str, *, headers: dict[str, str]) -> AsyncIterator[tuple[object, ...]]:
    async with (
        create_mcp_http_client(headers=headers) as http_client,
        streamable_http_client(url, http_client=http_client) as streams,
    ):
        yield streams


@asynccontextmanager
async def _production_sse(url: str, *, headers: dict[str, str]) -> AsyncIterator[tuple[object, ...]]:
    async with sse_client(url, headers=headers) as streams:
        yield streams


class McpClient:
    """Authenticated alphaXiv MCP client with only statically reviewed tools."""

    def __init__(
        self,
        *,
        _stream_factory: StreamFactory | None = None,
        _fallback_stream_factory: StreamFactory | None = None,
        _session_factory: SessionFactory = _production_session,
    ) -> None:
        api_key = os.getenv("ALPHAXIV_API_KEY", "").strip()
        if not api_key:
            msg = "ALPHAXIV_API_KEY is required for MCP commands"
            raise InputError(msg)
        if len(api_key) > 1_000 or any(ord(character) < 33 or ord(character) == 127 for character in api_key):
            msg = "ALPHAXIV_API_KEY is invalid"
            raise InputError(msg)
        using_production_stream = _stream_factory is None
        self._authorization = f"Bearer {api_key}"
        self._stream_factory = _stream_factory or _production_streamable
        if using_production_stream:
            self._fallback_stream_factory = _fallback_stream_factory or _production_sse
        else:
            self._fallback_stream_factory = _fallback_stream_factory
        self._session_factory = _session_factory
        self._stack: AsyncExitStack | None = None
        self._session: Session | None = None
        self._initialized = False
        self._closed = False

    async def __aenter__(self) -> "McpClient":
        if self._closed:
            msg = "MCP client cannot be reused after closing"
            raise RuntimeError(msg)
        if self._stack is not None:
            msg = "MCP client already has a managed session"
            raise RuntimeError(msg)
        try:
            await self._open_session(self._stream_factory)
        except BaseException as error:
            if isinstance(error, Exception) and self._can_fallback(error):
                try:
                    await self._open_fallback_session()
                except BaseException as fallback_error:
                    await self._mark_failed_connection()
                    if isinstance(fallback_error, Exception):
                        raise self._map_exception(fallback_error, fallback="MCP connection failed") from fallback_error
                    raise
            else:
                await self._mark_failed_connection()
                if isinstance(error, Exception):
                    raise self._map_exception(error, fallback="MCP connection failed") from error
                raise
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        await self._close_session()
        self._authorization = ""
        self._closed = True

    async def initialize(self) -> McpInitializeResult:
        try:
            initialized = await self._initialize_session()
        except ValidationError as error:
            raise InvalidResponseError.from_validation_error(error) from error
        except Exception as error:
            if not self._can_fallback(error):
                raise self._map_exception(error, fallback="MCP initialization failed") from error
            try:
                with suppress(Exception):
                    await self._close_session()
                await self._open_fallback_session()
                initialized = await self._initialize_session()
            except ValidationError as fallback_error:
                raise InvalidResponseError.from_validation_error(fallback_error) from fallback_error
            except Exception as fallback_error:
                raise self._map_exception(fallback_error, fallback="MCP initialization failed") from fallback_error
        self._initialized = True
        return initialized

    async def _initialize_session(self) -> McpInitializeResult:
        result = await self._managed_session().initialize()
        server = self._attribute(result, "server_info", "serverInfo")
        protocol_version = self._attribute(result, "protocol_version", "protocolVersion")
        server_name = self._attribute(server, "name")
        server_version = self._attribute(server, "version", default=None)
        return McpInitializeResult(
            protocol_version=str(protocol_version),
            server_name=str(server_name),
            server_version=str(server_version) if server_version is not None else None,
        )

    async def _open_session(self, stream_factory: StreamFactory) -> None:
        stack = AsyncExitStack()
        try:
            streams = await stack.enter_async_context(
                stream_factory(MCP_ENDPOINT, headers={"Authorization": self._authorization})
            )
            if len(streams) < 2:
                msg = "MCP transport did not provide read and write streams"
                raise RuntimeError(msg)
            session = await stack.enter_async_context(self._session_factory(streams[0], streams[1]))
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        self._session = session

    async def _open_fallback_session(self) -> None:
        stream_factory = self._fallback_stream_factory
        if stream_factory is None:
            msg = "MCP fallback transport is unavailable"
            raise RuntimeError(msg)
        self._fallback_stream_factory = None
        await self._open_session(stream_factory)

    async def _close_session(self) -> None:
        stack = self._stack
        self._session = None
        self._stack = None
        self._initialized = False
        if stack is not None:
            await stack.aclose()

    async def _mark_failed_connection(self) -> None:
        await self._close_session()
        self._authorization = ""
        self._closed = True

    def _can_fallback(self, error: Exception) -> bool:
        if self._fallback_stream_factory is None or self._initialized:
            return False
        mapped = self._map_exception(error, fallback="MCP transport failed")
        return not isinstance(mapped, InputError | InvalidResponseError | PermissionDeniedError | RateLimitError)

    async def list_tools(self) -> McpToolList:
        session = self._initialized_session()
        try:
            result = await session.list_tools()
            raw_tools = self._attribute(result, "tools")
            tools = []
            for tool in raw_tools:
                schema = self._attribute(tool, "input_schema", "inputSchema")
                properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
                required = schema.get("required", ()) if isinstance(schema, dict) else ()
                tools.append(
                    McpToolDescription(
                        name=str(self._attribute(tool, "name")),
                        description=self._optional_string(self._attribute(tool, "description", default=None)),
                        required_arguments=tuple(str(item) for item in required),
                        argument_names=tuple(str(item) for item in properties),
                    )
                )
            return McpToolList(tools=tuple(tools))
        except ValidationError as error:
            raise InvalidResponseError.from_validation_error(error) from error
        except RemoteAPIError:
            raise
        except Exception as error:
            raise self._map_exception(error, fallback="MCP tools/list failed") from error

    async def discover_papers(self, arguments: DiscoverPapersArguments) -> McpTextResult:
        return await self._call_text(McpToolName.DISCOVER_PAPERS, arguments)

    async def get_paper_content(self, arguments: GetPaperContentArguments) -> McpTextResult:
        return await self._call_text(McpToolName.GET_PAPER_CONTENT, arguments)

    async def answer_pdf_queries(self, arguments: AnswerPdfQueriesArguments) -> McpTextResult:
        return await self._call_text(McpToolName.ANSWER_PDF_QUERIES, arguments)

    async def read_github_files(self, arguments: GithubRepositoryArguments) -> McpTextResult:
        return await self._call_text(McpToolName.READ_GITHUB_FILES, arguments)

    async def list_library(self, arguments: ListLibraryArguments) -> LibraryListResult:
        result = await self._call_tool(MCP_TOOLS[McpToolName.LIST_LIBRARY], arguments)
        payload = self._result_payload(result)
        try:
            external = ExternalLibraryResponse.model_validate(payload)
        except ValidationError as error:
            raise InvalidResponseError.from_validation_error(error) from error
        return LibraryListResult.from_external(external)

    async def save_papers(self, arguments: SavePapersArguments) -> LibraryMutationResult:
        target = arguments.folder_id or "default"
        return await self._call_mutation(McpToolName.SAVE_PAPERS, arguments, target=target)

    async def remove_papers(self, arguments: RemovePapersArguments) -> LibraryMutationResult:
        return await self._call_mutation(McpToolName.REMOVE_PAPERS, arguments, target=arguments.folder_id)

    async def move_papers(self, arguments: MovePapersArguments) -> LibraryMutationResult:
        target = f"{arguments.from_folder_id} -> {arguments.to_folder_id}"
        return await self._call_mutation(McpToolName.MOVE_PAPERS, arguments, target=target)

    async def create_folder(self, arguments: CreateFolderArguments) -> LibraryMutationResult:
        return await self._call_mutation(McpToolName.CREATE_FOLDER, arguments, target=arguments.name)

    async def rename_folder(self, arguments: RenameFolderArguments) -> LibraryMutationResult:
        return await self._call_mutation(McpToolName.RENAME_FOLDER, arguments, target=arguments.folder_id)

    async def delete_folder(self, arguments: DeleteFolderArguments) -> LibraryMutationResult:
        return await self._call_mutation(McpToolName.DELETE_FOLDER, arguments, target=arguments.folder_id)

    async def _call_text(self, name: McpToolName, arguments: McpArguments) -> McpTextResult:
        result = await self._call_tool(MCP_TOOLS[name], arguments)
        return McpTextResult(
            tool=name.value,
            text=self._result_text(result),
            metadata=self._safe_metadata(result),
        )

    async def _call_mutation(
        self,
        name: McpToolName,
        arguments: McpArguments,
        *,
        target: str,
    ) -> LibraryMutationResult:
        result = await self._call_tool(MCP_TOOLS[name], arguments)
        payload = self._optional_result_payload(result)
        affected = self._affected_count(payload)
        return LibraryMutationResult(
            action=name.value,
            success=True,
            target=target,
            affected_count=affected,
            message=self._result_text(result)[:2_000] or None,
            details=self._safe_details(payload),
        )

    async def _call_tool(self, contract: McpToolContract, arguments: McpArguments) -> object:
        if not isinstance(arguments, contract.arguments_model):
            msg = f"invalid arguments for {contract.name.value}"
            raise TypeError(msg)
        session = self._initialized_session()
        payload = arguments.model_dump(by_alias=True, exclude_defaults=True, exclude_none=True, mode="json")
        try:
            result = await session.call_tool(contract.name.value, payload)
        except Exception as error:
            fallback = f"MCP tool {contract.name.value} failed"
            raise self._map_exception(error, fallback=fallback) from error
        if bool(self._attribute(result, "is_error", "isError", default=False)):
            message = self._result_text(result) or f"MCP tool {contract.name.value} failed"
            if "quota" in message.lower() or "rate limit" in message.lower():
                raise RateLimitError(message)
            raise RemoteAPIError(message)
        return result

    def _managed_session(self) -> Session:
        if self._session is None:
            msg = "MCP client requires a managed session"
            raise RuntimeError(msg)
        return self._session

    def _initialized_session(self) -> Session:
        session = self._managed_session()
        if not self._initialized:
            msg = "MCP session must initialize before listing or calling tools"
            raise RuntimeError(msg)
        return session

    @classmethod
    def _result_text(cls, result: object) -> str:
        content = cls._attribute(result, "content", default=())
        texts = []
        for item in content:
            if cls._attribute(item, "type", default=None) == "text":
                text = cls._attribute(item, "text", default=None)
                if isinstance(text, str):
                    texts.append(text)
        return "\n".join(texts)

    @classmethod
    def _result_payload(cls, result: object) -> dict[str, object]:
        structured = cls._attribute(result, "structured_content", "structuredContent", default=None)
        if isinstance(structured, dict) and structured:
            return structured
        text = cls._result_text(result)
        try:
            payload = json.loads(text)
        except ValueError as error:
            raise InvalidResponseError("MCP tool returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise InvalidResponseError("MCP tool returned an invalid response")
        return payload

    @classmethod
    def _optional_result_payload(cls, result: object) -> dict[str, object]:
        structured = cls._attribute(result, "structured_content", "structuredContent", default=None)
        if isinstance(structured, dict) and structured:
            return structured
        try:
            payload = json.loads(cls._result_text(result))
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _safe_metadata(cls, result: object) -> dict[str, JsonValue]:
        structured = cls._attribute(result, "structured_content", "structuredContent", default=None)
        if not isinstance(structured, dict):
            return {}
        allowed = {"requestId", "request_id", "model", "paperId", "paper_id"}
        return {
            key: cls._sanitize_json(value)
            for key, value in structured.items()
            if key in allowed and cls._is_json_value(value)
        }

    @classmethod
    def _safe_details(cls, payload: dict[str, object]) -> dict[str, JsonValue]:
        details = cls._sanitize_json(payload)
        return details if isinstance(details, dict) else {}

    @classmethod
    def _sanitize_json(cls, value: object) -> JsonValue:
        if isinstance(value, dict):
            sanitized: dict[str, JsonValue] = {}
            for key, item in value.items():
                if isinstance(key, str) and not is_sensitive_key(key):
                    sanitized[key] = cls._sanitize_json(item)
            return sanitized
        if isinstance(value, list | tuple):
            return [cls._sanitize_json(item) for item in value]
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        return str(value)[:500]

    @staticmethod
    def _affected_count(payload: dict[str, object]) -> int | None:
        for key in ("affected_count", "moved_count", "added_count", "removed_count", "count"):
            value = payload.get(key)
            if isinstance(value, int) and value >= 0:
                return value
        return None

    @staticmethod
    def _is_json_value(value: object) -> TypeGuard[JsonValue]:
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _attribute(
        value: object,
        *names: str,
        default: Any = ...,  # noqa: ANN401 - external MCP response objects are duck typed.
    ) -> Any:  # noqa: ANN401 - callers validate every returned value.
        for name in names:
            if isinstance(value, dict) and name in value:
                return value[name]
            if hasattr(value, name):
                return getattr(value, name)
        if default is not ...:
            return default
        msg = f"MCP response is missing {names[0]}"
        raise InvalidResponseError(msg)

    @classmethod
    def _map_exception(cls, error: Exception, *, fallback: str) -> AlphaXivError:
        if isinstance(error, AlphaXivError):
            return error
        statuses = cls._status_codes(error)
        if statuses.intersection({401, 403}):
            return PermissionDeniedError("MCP authentication failed")
        if 429 in statuses:
            return RateLimitError("alphaXiv MCP rate limit or quota was exhausted")
        return RemoteAPIError(fallback)

    @classmethod
    def _status_codes(cls, error: BaseException) -> set[int]:
        statuses: set[int] = set()
        pending = [error]
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            response = getattr(current, "response", None)
            status = getattr(response, "status_code", None)
            if isinstance(status, int):
                statuses.add(status)
            if isinstance(current, BaseExceptionGroup):
                pending.extend(current.exceptions)
            if current.__cause__ is not None:
                pending.append(current.__cause__)
            if current.__context__ is not None:
                pending.append(current.__context__)
        return statuses

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) else None
