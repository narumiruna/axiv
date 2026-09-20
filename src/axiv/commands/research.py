from typing import Annotated

import typer

from axiv.commands.common import emit
from axiv.commands.common import run_mcp_operation
from axiv.commands.common import run_operation
from axiv.models.mcp import DiscoverPapersArguments
from axiv.models.mcp import DiscoverPrioritize
from axiv.models.mcp import McpTextResult
from axiv.output import render_text

app = typer.Typer(help="Run quota-consuming alphaXiv research tools.", no_args_is_help=True)


@app.command("discover")
def discover(
    question: Annotated[str, typer.Argument(help="Research question in the user's own terms.")],
    keyword: Annotated[
        list[str] | None,
        typer.Option("--keyword", help="Repeat for each user-supplied keyword."),
    ] = None,
    difficulty: Annotated[int, typer.Option(min=1, max=10, help="Retrieval effort from 1 to 10.")] = 5,
    published_after: Annotated[str | None, typer.Option(help="Inclusive YYYY-MM-DD lower bound.")] = None,
    published_before: Annotated[str | None, typer.Option(help="Inclusive YYYY-MM-DD upper bound.")] = None,
    prioritize: Annotated[
        DiscoverPrioritize,
        typer.Option(case_sensitive=False, help="Result prioritization."),
    ] = DiscoverPrioritize.DEFAULT,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Discover papers with an Assistant-quota research call."""

    def operation() -> McpTextResult:
        arguments = DiscoverPapersArguments.model_validate(
            {
                "keywords": tuple(keyword or ()),
                "question": question,
                "difficulty": difficulty,
                "published_after": published_after,
                "published_before": published_before,
                "prioritize": prioritize,
            }
        )
        return run_mcp_operation(lambda client: client.discover_papers(arguments))

    result = run_operation(operation)
    emit(result, json_output=json_output, human=lambda: render_text(result.text))
