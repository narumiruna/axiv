import asyncio
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

import axiv.commands.common as common_command
from axiv.clients.mcp import McpClient
from axiv.models.mcp import GetPaperContentArguments
from axiv.models.mcp import McpTextResult


@pytest.mark.parametrize("failure_phase", [None, "initialize", "tool"])
@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
def test_mcp_runner_initializes_once_closes_and_never_retries(monkeypatch, failure_phase, error_type):
    client = MagicMock(spec=McpClient)
    client.__aenter__.return_value = client
    result = McpTextResult(tool="get_paper_content", text="content")
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(common_command, "McpClient", factory)
    arguments = GetPaperContentArguments(url="https://arxiv.org/abs/1706.03762")
    events = []

    async def initialize():
        events.append("initialize")
        if failure_phase == "initialize":
            raise error_type("initialize failed")

    async def call(_arguments):
        events.append("tool")
        if failure_phase == "tool":
            raise error_type("tool failed")
        return result

    async def close(*_args):
        events.append("close")
        return False

    client.initialize = AsyncMock(side_effect=initialize)
    client.get_paper_content = AsyncMock(side_effect=call)
    client.__aexit__ = AsyncMock(side_effect=close)

    def run():
        return common_command.run_mcp_operation(lambda active: active.get_paper_content(arguments))

    if failure_phase is None:
        assert run() is result
    else:
        with pytest.raises(error_type, match=f"{failure_phase} failed"):
            run()

    factory.assert_called_once_with()
    client.__aenter__.assert_awaited_once_with()
    client.initialize.assert_awaited_once_with()
    client.__aexit__.assert_awaited_once()
    if failure_phase == "initialize":
        client.get_paper_content.assert_not_awaited()
        assert events == ["initialize", "close"]
    else:
        client.get_paper_content.assert_awaited_once_with(arguments)
        assert events == ["initialize", "tool", "close"]
