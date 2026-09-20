from typing import Annotated

import typer

from axiv.clients.public_rest import PublicRestClient
from axiv.commands.common import emit
from axiv.commands.common import run_operation
from axiv.models.search import FullTextSearchResults
from axiv.models.search import OrganizationResults
from axiv.models.search import PaperSearchResults
from axiv.models.search import TopicSuggestions
from axiv.output import render_table

app = typer.Typer(help="Search alphaXiv's public paper and organization indexes.", no_args_is_help=True)


@app.command("papers")
def papers(
    query: Annotated[str, typer.Argument(help="Keyword query.")],
    limit: Annotated[int, typer.Option(min=1, max=50, help="Maximum results to print.")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Search public papers by keywords."""

    def operation() -> PaperSearchResults:
        with PublicRestClient() as client:
            result = client.search_papers(query)
        return PaperSearchResults.from_items(result.items[:limit])

    result = run_operation(operation)
    emit(
        result,
        json_output=json_output,
        human=lambda: render_table(
            title="Papers",
            columns=("Paper ID", "Title", "Snippet"),
            rows=[(item.paper_id, item.title, item.snippet) for item in result.items],
        ),
    )


@app.command("full-text")
def full_text(
    query: Annotated[str, typer.Argument(help="Full-text query.")],
    limit: Annotated[int, typer.Option(min=1, max=50, help="Maximum results.")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Search extracted paper text."""

    def operation() -> FullTextSearchResults:
        with PublicRestClient() as client:
            return client.search_full_text(query, limit=limit)

    result = run_operation(operation)
    emit(
        result,
        json_output=json_output,
        human=lambda: render_table(
            title="Full-text results",
            columns=("Paper ID", "Title", "Votes"),
            rows=[(item.paper_id, item.title, item.votes) for item in result.items],
        ),
    )


@app.command("topics")
def topics(
    query: Annotated[str, typer.Argument(help="Topic query.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Suggest alphaXiv topics."""

    def operation() -> TopicSuggestions:
        with PublicRestClient() as client:
            return client.closest_topics(query)

    result = run_operation(operation)
    emit(
        result,
        json_output=json_output,
        human=lambda: render_table(
            title="Topics",
            columns=("Topic",),
            rows=[(topic,) for topic in result.data],
        ),
    )


@app.command("organizations")
def organizations(
    query: Annotated[str, typer.Argument(help="Organization query.")],
    limit: Annotated[int, typer.Option(min=1, max=50, help="Maximum results to print.")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Search research organizations."""

    def operation() -> OrganizationResults:
        with PublicRestClient() as client:
            result = client.search_organizations(query)
        return OrganizationResults.from_items(result.items[:limit])

    result = run_operation(operation)
    emit(
        result,
        json_output=json_output,
        human=lambda: render_table(
            title="Organizations",
            columns=("Name", "Slug"),
            rows=[(item.name, item.slug) for item in result.items],
        ),
    )
