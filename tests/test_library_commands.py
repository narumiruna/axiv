import json
from typing import Self

import pytest
from typer.testing import CliRunner

import axiv.commands.common as common_command
from axiv.cli import app
from axiv.models.library import LibraryFolder
from axiv.models.library import LibraryListResult
from axiv.models.library import LibraryMutationResult
from axiv.models.library import LibraryPaper
from axiv.models.library import PaperMembership
from axiv.models.mcp import CreateFolderArguments
from axiv.models.mcp import DeleteFolderArguments
from axiv.models.mcp import ListLibraryArguments
from axiv.models.mcp import McpInitializeResult
from axiv.models.mcp import MovePapersArguments
from axiv.models.mcp import RemovePapersArguments
from axiv.models.mcp import RenameFolderArguments
from axiv.models.mcp import SavePapersArguments

runner = CliRunner()


class FakeMcpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.created = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.calls.append(("close", None))

    async def initialize(self) -> McpInitializeResult:
        self.calls.append(("initialize", None))
        return McpInitializeResult(protocol_version="2025-03-26", server_name="alphaXiv")

    async def list_library(self, arguments: ListLibraryArguments) -> LibraryListResult:
        self.calls.append(("list_library", arguments))
        folder = LibraryFolder(
            folder_id="folder-1",
            name="Reading",
            type="custom",
            paper_count=1,
            papers=(LibraryPaper(paper_id="paper-1", title="Attention paper", url="https://arxiv.org/abs/1706.03762"),),
        )
        membership = PaperMembership(paper_id="paper-1", folder_ids=("folder-1", "folder-2"))
        return LibraryListResult(folders=(folder,), memberships=(membership,))

    def _mutation(self, name: str, arguments: object) -> LibraryMutationResult:
        self.calls.append((name, arguments))
        return LibraryMutationResult(action=name, success=True, target="target", affected_count=1)

    async def save_papers(self, arguments: SavePapersArguments) -> LibraryMutationResult:
        return self._mutation("save_papers", arguments)

    async def remove_papers(self, arguments: RemovePapersArguments) -> LibraryMutationResult:
        return self._mutation("remove_papers", arguments)

    async def move_papers(self, arguments: MovePapersArguments) -> LibraryMutationResult:
        return self._mutation("move_papers", arguments)

    async def create_folder(self, arguments: CreateFolderArguments) -> LibraryMutationResult:
        return self._mutation("create_folder", arguments)

    async def rename_folder(self, arguments: RenameFolderArguments) -> LibraryMutationResult:
        return self._mutation("rename_folder", arguments)

    async def delete_folder(self, arguments: DeleteFolderArguments) -> LibraryMutationResult:
        return self._mutation("delete_folder", arguments)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeMcpClient:
    fake = FakeMcpClient()

    def create() -> FakeMcpClient:
        fake.created += 1
        return fake

    monkeypatch.setattr(common_command, "McpClient", create)
    return fake


@pytest.mark.parametrize(
    "command",
    [
        ["library", "list"],
        ["library", "save"],
        ["library", "remove"],
        ["library", "move"],
        ["library", "folder", "create"],
        ["library", "folder", "rename"],
        ["library", "folder", "delete"],
    ],
)
def test_library_commands_have_offline_help(command: list[str]) -> None:
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0


def test_library_list_defaults_to_no_papers_and_supports_explicit_loading(fake_client: FakeMcpClient) -> None:
    default = runner.invoke(app, ["library", "list", "--json"])
    default_arguments = fake_client.calls[1][1]
    fake_client.calls.clear()
    included = runner.invoke(app, ["library", "list", "--include-papers", "--json"])
    included_arguments = fake_client.calls[1][1]

    assert default.exit_code == 0
    assert included.exit_code == 0
    assert json.loads(default.stdout)["folders"][0]["folder_id"] == "folder-1"
    assert isinstance(default_arguments, ListLibraryArguments)
    assert default_arguments.include_papers is False
    assert isinstance(included_arguments, ListLibraryArguments)
    assert included_arguments.include_papers is True


def test_library_list_human_output_displays_only_requested_details(fake_client: FakeMcpClient) -> None:
    default = runner.invoke(app, ["library", "list"])
    included = runner.invoke(app, ["library", "list", "--include-papers"])
    membership = runner.invoke(app, ["library", "list", "--paper", "paper-1"])

    assert default.exit_code == 0
    assert included.exit_code == 0
    assert membership.exit_code == 0
    assert "Attention paper" not in default.stdout
    assert "paper-1" not in default.stdout
    assert "Attention paper" in included.stdout
    assert "paper-1" in included.stdout
    assert "folder-2" not in included.stdout
    assert "paper-1" in membership.stdout
    assert "folder-1, folder-2" in membership.stdout
    assert "Attention paper" not in membership.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["library", "save", "folder-1", "1706.03762"],
        ["library", "remove", "folder-1", "1706.03762"],
        ["library", "move", "folder-1", "folder-2", "1706.03762"],
        ["library", "folder", "create", "Reading"],
        ["library", "folder", "rename", "folder-1", "Read next"],
        ["library", "folder", "delete", "folder-1"],
    ],
)
def test_every_write_requires_yes_before_opening_client(args: list[str], fake_client: FakeMcpClient) -> None:
    result = runner.invoke(app, args)

    assert result.exit_code == 2
    assert json.loads(result.stderr)["error"]["code"] == "invalid_input"
    assert "--yes" in result.stderr
    assert fake_client.created == 0
    assert fake_client.calls == []


@pytest.mark.parametrize(
    ("args", "expected_method", "argument_type"),
    [
        (
            ["library", "save", "folder-1", "1706.03762", "--yes", "--json"],
            "save_papers",
            SavePapersArguments,
        ),
        (
            ["library", "remove", "folder-1", "1706.03762", "--yes", "--json"],
            "remove_papers",
            RemovePapersArguments,
        ),
        (
            ["library", "move", "folder-1", "folder-2", "1706.03762", "--yes", "--json"],
            "move_papers",
            MovePapersArguments,
        ),
        (
            ["library", "folder", "create", "Reading", "--yes", "--json"],
            "create_folder",
            CreateFolderArguments,
        ),
        (
            ["library", "folder", "rename", "folder-1", "Read next", "--yes", "--json"],
            "rename_folder",
            RenameFolderArguments,
        ),
        (
            ["library", "folder", "delete", "folder-1", "--yes", "--json"],
            "delete_folder",
            DeleteFolderArguments,
        ),
    ],
)
def test_confirmed_write_calls_only_expected_method_once(
    args: list[str],
    expected_method: str,
    argument_type: type[object],
    fake_client: FakeMcpClient,
) -> None:
    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert json.loads(result.stdout)["success"] is True
    assert fake_client.created == 1
    assert [name for name, _ in fake_client.calls] == ["initialize", expected_method, "close"]
    assert isinstance(fake_client.calls[1][1], argument_type)
