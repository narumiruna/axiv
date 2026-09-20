import asyncio
from collections.abc import Awaitable
from collections.abc import Callable
from contextvars import ContextVar

import typer
from pydantic import BaseModel

from axiv.clients.mcp import McpClient
from axiv.errors import AlphaXivError
from axiv.errors import InputError
from axiv.errors import RemoteAPIError
from axiv.output import render_error
from axiv.output import render_json

_DEBUG = ContextVar("axiv_debug", default=False)


def set_debug(enabled: bool) -> None:
    _DEBUG.set(enabled)


def run_mcp_operation[ModelT: BaseModel](
    operation: Callable[[McpClient], Awaitable[ModelT]],
) -> ModelT:
    async def execute() -> ModelT:
        async with McpClient() as client:
            await client.initialize()
            return await operation(client)

    return asyncio.run(execute())


def run_operation[ModelT: BaseModel](operation: Callable[[], ModelT]) -> ModelT:
    try:
        return operation()
    except AlphaXivError as error:
        render_error(error)
        raise typer.Exit(code=int(error.exit_code)) from None
    except ValueError as error:
        safe_error = InputError(str(error))
        render_error(safe_error)
        raise typer.Exit(code=int(safe_error.exit_code)) from None
    except Exception as error:
        if _DEBUG.get():
            raise
        safe_error = RemoteAPIError("unexpected axiv CLI error")
        render_error(safe_error)
        raise typer.Exit(code=int(safe_error.exit_code)) from error


def emit(model: BaseModel, *, json_output: bool, human: Callable[[], None]) -> None:
    if json_output:
        render_json(model)
    else:
        human()
