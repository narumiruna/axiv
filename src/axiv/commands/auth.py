import asyncio
import os
from typing import Annotated

import typer

from axiv.clients.mcp import McpClient
from axiv.commands.common import emit
from axiv.commands.common import run_operation
from axiv.contracts.mcp import check_mcp_tools
from axiv.errors import ToolDriftError
from axiv.models.mcp import AuthStatusResult
from axiv.output import render_table

app = typer.Typer(help="Check alphaXiv MCP authentication and static tool compatibility.", no_args_is_help=True)


async def _status() -> AuthStatusResult:
    async with McpClient() as client:
        initialized = await client.initialize()
        drift = check_mcp_tools(await client.list_tools())
    if not drift.compatible:
        issue_summary = "; ".join(f"{issue.tool} {issue.kind}: {issue.detail}" for issue in drift.issues)
        raise ToolDriftError(
            f"alphaXiv MCP tool contract drift detected ({len(drift.issues)} issues): {issue_summary}"
        )
    return AuthStatusResult(
        api_key_present=bool(os.getenv("ALPHAXIV_API_KEY", "").strip()),
        initialized=True,
        tools_compatible=True,
        protocol_version=initialized.protocol_version,
        server_name=initialized.server_name,
        issue_count=0,
    )


@app.command("status")
def status(
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Validate ALPHAXIV_API_KEY without displaying it."""

    result = run_operation(lambda: asyncio.run(_status()))
    emit(
        result,
        json_output=json_output,
        human=lambda: render_table(
            title="alphaXiv MCP status",
            columns=("API key", "Initialized", "Tools", "Protocol", "Server"),
            rows=[
                (
                    "present" if result.api_key_present else "missing",
                    "yes" if result.initialized else "no",
                    "compatible" if result.tools_compatible else "drift",
                    result.protocol_version,
                    result.server_name,
                )
            ],
        ),
    )
