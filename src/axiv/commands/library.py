from typing import Annotated

import typer

from axiv.commands.common import emit
from axiv.commands.common import run_mcp_operation
from axiv.commands.common import run_operation
from axiv.errors import InputError
from axiv.models.library import LibraryListResult
from axiv.models.library import LibraryMutationResult
from axiv.models.mcp import CreateFolderArguments
from axiv.models.mcp import DeleteFolderArguments
from axiv.models.mcp import ListLibraryArguments
from axiv.models.mcp import MovePapersArguments
from axiv.models.mcp import RemovePapersArguments
from axiv.models.mcp import RenameFolderArguments
from axiv.models.mcp import SavePapersArguments
from axiv.output import render_table

app = typer.Typer(help="Read and manage the authenticated alphaXiv library.", no_args_is_help=True)
folder_app = typer.Typer(help="Manage custom alphaXiv library folders.", no_args_is_help=True)
app.add_typer(folder_app, name="folder")


def _require_confirmation(yes: bool, *, target: str) -> None:
    if not yes:
        raise InputError(f"remote library write for {target} requires --yes")


def _render_library(
    result: LibraryListResult,
    *,
    include_papers: bool,
    include_memberships: bool,
) -> None:
    render_table(
        title="alphaXiv library",
        columns=("Folder ID", "Name", "Type", "Papers", "Parent"),
        rows=[
            (folder.folder_id, folder.name, folder.type, folder.paper_count, folder.parent_id)
            for folder in result.folders
        ],
    )
    if include_papers:
        render_table(
            title="alphaXiv library papers",
            columns=("Folder ID", "Paper ID", "Title", "URL"),
            rows=[
                (folder.folder_id, paper.paper_id, paper.title, paper.url)
                for folder in result.folders
                for paper in folder.papers
            ],
        )
    if include_memberships:
        render_table(
            title="alphaXiv paper memberships",
            columns=("Paper ID", "Folder IDs"),
            rows=[(membership.paper_id, ", ".join(membership.folder_ids)) for membership in result.memberships],
        )


def _emit_mutation(result: LibraryMutationResult, *, json_output: bool) -> None:
    emit(
        result,
        json_output=json_output,
        human=lambda: render_table(
            title="alphaXiv library update",
            columns=("Action", "Target", "Success", "Affected", "Message"),
            rows=[
                (
                    result.action,
                    result.target,
                    "yes" if result.success else "no",
                    result.affected_count,
                    result.message,
                )
            ],
        ),
    )


@app.command("list")
def list_library(
    include_papers: Annotated[
        bool,
        typer.Option("--include-papers", help="Load capped paper details for each folder."),
    ] = False,
    paper: Annotated[
        list[str] | None,
        typer.Option("--paper", help="Repeat to report folder membership for specific papers."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """List library folders without paper details by default."""

    def operation() -> LibraryListResult:
        arguments = ListLibraryArguments(include_papers=include_papers, paper_ids_or_urls=tuple(paper or ()))
        return run_mcp_operation(lambda client: client.list_library(arguments))

    result = run_operation(operation)
    emit(
        result,
        json_output=json_output,
        human=lambda: _render_library(
            result,
            include_papers=include_papers,
            include_memberships=bool(paper),
        ),
    )


@app.command("save")
def save(
    folder: Annotated[str, typer.Argument(help="Target folder ID.")],
    papers: Annotated[list[str], typer.Argument(help="One or more arXiv IDs or URLs.")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm this remote write.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Save papers to one folder after explicit confirmation."""

    def operation() -> LibraryMutationResult:
        _require_confirmation(yes, target=f"folder {folder}")
        arguments = SavePapersArguments(folder_id=folder, paper_ids_or_urls=tuple(papers))
        return run_mcp_operation(lambda client: client.save_papers(arguments))

    _emit_mutation(run_operation(operation), json_output=json_output)


@app.command("remove")
def remove(
    folder: Annotated[str, typer.Argument(help="Folder ID to remove papers from.")],
    papers: Annotated[list[str], typer.Argument(help="One or more arXiv IDs or URLs.")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm this remote write.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Remove papers from one folder after explicit confirmation."""

    def operation() -> LibraryMutationResult:
        _require_confirmation(yes, target=f"folder {folder}")
        arguments = RemovePapersArguments(folder_id=folder, paper_ids_or_urls=tuple(papers))
        return run_mcp_operation(lambda client: client.remove_papers(arguments))

    _emit_mutation(run_operation(operation), json_output=json_output)


@app.command("move")
def move(
    source: Annotated[str, typer.Argument(help="Source folder ID.")],
    target: Annotated[str, typer.Argument(help="Target folder ID.")],
    papers: Annotated[list[str], typer.Argument(help="One or more arXiv IDs or URLs.")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm this remote write.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Move papers between folders after explicit confirmation."""

    def operation() -> LibraryMutationResult:
        _require_confirmation(yes, target=f"folders {source} -> {target}")
        arguments = MovePapersArguments(
            from_folder_id=source,
            to_folder_id=target,
            paper_ids_or_urls=tuple(papers),
        )
        return run_mcp_operation(lambda client: client.move_papers(arguments))

    _emit_mutation(run_operation(operation), json_output=json_output)


@folder_app.command("create")
def create_folder(
    name: Annotated[str, typer.Argument(help="New folder name.")],
    parent: Annotated[str | None, typer.Option("--parent", help="Optional parent folder ID.")] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm this remote write.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Create a custom folder after explicit confirmation."""

    def operation() -> LibraryMutationResult:
        _require_confirmation(yes, target=f"new folder {name}")
        arguments = CreateFolderArguments(name=name, parent_folder_id=parent)
        return run_mcp_operation(lambda client: client.create_folder(arguments))

    _emit_mutation(run_operation(operation), json_output=json_output)


@folder_app.command("rename")
def rename_folder(
    folder: Annotated[str, typer.Argument(help="Custom folder ID.")],
    name: Annotated[str, typer.Argument(help="New folder name.")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm this remote write.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Rename a custom folder after explicit confirmation."""

    def operation() -> LibraryMutationResult:
        _require_confirmation(yes, target=f"folder {folder} as {name}")
        arguments = RenameFolderArguments(folder_id=folder, name=name)
        return run_mcp_operation(lambda client: client.rename_folder(arguments))

    _emit_mutation(run_operation(operation), json_output=json_output)


@folder_app.command("delete")
def delete_folder(
    folder: Annotated[str, typer.Argument(help="Folder ID to delete with its memberships.")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm this destructive remote write.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Delete a folder and its memberships after explicit confirmation."""

    def operation() -> LibraryMutationResult:
        _require_confirmation(yes, target=f"folder {folder} and its memberships")
        arguments = DeleteFolderArguments(folder_id=folder)
        return run_mcp_operation(lambda client: client.delete_folder(arguments))

    _emit_mutation(run_operation(operation), json_output=json_output)
