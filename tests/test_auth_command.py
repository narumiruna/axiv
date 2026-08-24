import json
from typing import Self

import pytest
from typer.testing import CliRunner

import axiv.commands.auth as auth_command
from axiv.cli import app
from axiv.errors import PermissionDeniedError
from axiv.models.mcp import McpInitializeResult
from axiv.models.mcp import McpToolDescription
from axiv.models.mcp import McpToolList

runner = CliRunner()


class FakeMcpClient:
    def __init__(self) -> None:
        self.initialize_error: Exception | None = None
        self.tools = McpToolList(tools=())
        self.calls: list[str] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.calls.append("close")

    async def initialize(self) -> McpInitializeResult:
        self.calls.append("initialize")
        if self.initialize_error is not None:
            raise self.initialize_error
        return McpInitializeResult(protocol_version="2025-03-26", server_name="alphaXiv")

    async def list_tools(self) -> McpToolList:
        self.calls.append("list_tools")
        return self.tools


def compatible_tools() -> McpToolList:
    from axiv.contracts.mcp import MCP_TOOLS

    return McpToolList(
        tools=tuple(
            McpToolDescription(
                name=contract.name.value,
                required_arguments=contract.required_arguments,
                argument_names=contract.argument_names,
            )
            for contract in MCP_TOOLS.values()
        )
    )


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeMcpClient:
    fake = FakeMcpClient()
    monkeypatch.setattr(auth_command, "McpClient", lambda: fake)
    return fake


def test_auth_status_help_never_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPHAXIV_API_KEY", raising=False)

    result = runner.invoke(app, ["auth", "status", "--help"])

    assert result.exit_code == 0
    assert "ALPHAXIV_API_KEY" in result.stdout


def test_auth_status_distinguishes_missing_key_without_disclosing_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPHAXIV_API_KEY", raising=False)

    result = runner.invoke(app, ["auth", "status", "--json"])

    assert result.exit_code == 2
    assert json.loads(result.stderr)["error"]["code"] == "invalid_input"
    assert "Bearer" not in result.stderr


def test_auth_status_distinguishes_authentication_failure(
    fake_client: FakeMcpClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-private-value")
    fake_client.initialize_error = PermissionDeniedError("MCP authentication failed")

    result = runner.invoke(app, ["auth", "status", "--json"])

    assert result.exit_code == 3
    assert json.loads(result.stderr)["error"]["code"] == "permission_denied"
    assert "axv-private-value" not in result.stderr
    assert fake_client.calls == ["initialize", "close"]


def test_auth_status_distinguishes_tool_drift(fake_client: FakeMcpClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-private-value")
    fake_client.tools = McpToolList(
        tools=(McpToolDescription(name="unknown", required_arguments=(), argument_names=()),)
    )

    result = runner.invoke(app, ["auth", "status", "--json"])

    assert result.exit_code == 6
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "tool_drift"
    assert "missing_tool: reviewed tool is missing" in error["message"]
    assert "unknown_tool" not in error["message"]
    assert "axv-private-value" not in result.stderr
    assert fake_client.calls == ["initialize", "list_tools", "close"]


def test_auth_status_success_returns_stable_safe_result(
    fake_client: FakeMcpClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALPHAXIV_API_KEY", "axv-private-value")
    fake_client.tools = compatible_tools()

    result = runner.invoke(app, ["auth", "status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "api_key_present": True,
        "initialized": True,
        "tools_compatible": True,
        "protocol_version": "2025-03-26",
        "server_name": "alphaXiv",
        "issue_count": 0,
    }
    assert "axv-private-value" not in result.stdout
    assert fake_client.calls == ["initialize", "list_tools", "close"]
