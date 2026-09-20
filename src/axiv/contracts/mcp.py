from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import ConfigDict

from axiv.models.common import StrictModel
from axiv.models.mcp import AnswerPdfQueriesArguments
from axiv.models.mcp import CreateFolderArguments
from axiv.models.mcp import DeleteFolderArguments
from axiv.models.mcp import DiscoverPapersArguments
from axiv.models.mcp import GetPaperContentArguments
from axiv.models.mcp import GithubRepositoryArguments
from axiv.models.mcp import ListLibraryArguments
from axiv.models.mcp import McpArguments
from axiv.models.mcp import McpToolDriftIssue
from axiv.models.mcp import McpToolDriftReport
from axiv.models.mcp import McpToolList
from axiv.models.mcp import MovePapersArguments
from axiv.models.mcp import RemovePapersArguments
from axiv.models.mcp import RenameFolderArguments
from axiv.models.mcp import SavePapersArguments

MCP_ENDPOINT = "https://api.alphaxiv.org/mcp/v1"


class McpToolName(StrEnum):
    DISCOVER_PAPERS = "discover_papers"
    GET_PAPER_CONTENT = "get_paper_content"
    ANSWER_PDF_QUERIES = "answer_pdf_queries"
    READ_GITHUB_FILES = "read_files_from_github_repository"
    LIST_LIBRARY = "list_library"
    SAVE_PAPERS = "save_papers_to_folder"
    REMOVE_PAPERS = "remove_papers_from_folder"
    MOVE_PAPERS = "move_papers_between_folders"
    CREATE_FOLDER = "create_folder"
    RENAME_FOLDER = "rename_folder"
    DELETE_FOLDER = "delete_folder"


class McpAccess(StrEnum):
    READ = "read"
    WRITE = "write"


class McpQuota(StrEnum):
    NONE = "none"
    ASSISTANT = "assistant"


class McpToolContract(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    name: McpToolName
    access: McpAccess
    quota: McpQuota
    arguments_model: type[McpArguments]

    @property
    def required_arguments(self) -> tuple[str, ...]:
        schema = self.arguments_model.model_json_schema(by_alias=True)
        return tuple(schema.get("required", ()))

    @property
    def argument_names(self) -> tuple[str, ...]:
        schema = self.arguments_model.model_json_schema(by_alias=True)
        properties = schema.get("properties", {})
        return tuple(properties)


def _contract(
    name: McpToolName,
    arguments_model: type[McpArguments],
    *,
    access: McpAccess = McpAccess.READ,
    quota: McpQuota = McpQuota.NONE,
) -> McpToolContract:
    return McpToolContract(
        name=name,
        access=access,
        quota=quota,
        arguments_model=arguments_model,
    )


_CONTRACTS = (
    _contract(
        McpToolName.DISCOVER_PAPERS,
        DiscoverPapersArguments,
        quota=McpQuota.ASSISTANT,
    ),
    _contract(
        McpToolName.GET_PAPER_CONTENT,
        GetPaperContentArguments,
        quota=McpQuota.ASSISTANT,
    ),
    _contract(
        McpToolName.ANSWER_PDF_QUERIES,
        AnswerPdfQueriesArguments,
        quota=McpQuota.ASSISTANT,
    ),
    _contract(
        McpToolName.READ_GITHUB_FILES,
        GithubRepositoryArguments,
        quota=McpQuota.ASSISTANT,
    ),
    _contract(McpToolName.LIST_LIBRARY, ListLibraryArguments),
    _contract(
        McpToolName.SAVE_PAPERS,
        SavePapersArguments,
        access=McpAccess.WRITE,
    ),
    _contract(
        McpToolName.REMOVE_PAPERS,
        RemovePapersArguments,
        access=McpAccess.WRITE,
    ),
    _contract(
        McpToolName.MOVE_PAPERS,
        MovePapersArguments,
        access=McpAccess.WRITE,
    ),
    _contract(
        McpToolName.CREATE_FOLDER,
        CreateFolderArguments,
        access=McpAccess.WRITE,
    ),
    _contract(
        McpToolName.RENAME_FOLDER,
        RenameFolderArguments,
        access=McpAccess.WRITE,
    ),
    _contract(
        McpToolName.DELETE_FOLDER,
        DeleteFolderArguments,
        access=McpAccess.WRITE,
    ),
)

MCP_TOOLS: Mapping[McpToolName, McpToolContract] = MappingProxyType(
    {contract.name: contract for contract in _CONTRACTS}
)


def check_mcp_tools(candidate: McpToolList) -> McpToolDriftReport:
    remote_by_name = {tool.name: tool for tool in candidate.tools}
    expected_names = {name.value for name in MCP_TOOLS}

    issues = [
        McpToolDriftIssue(kind="missing_tool", tool=name, detail="reviewed tool is missing")
        for name in sorted(expected_names - remote_by_name.keys())
    ]

    for name, contract in MCP_TOOLS.items():
        remote = remote_by_name.get(name.value)
        if remote is None:
            continue
        if set(remote.required_arguments) != set(contract.required_arguments):
            issues.append(
                McpToolDriftIssue(
                    kind="required_arguments",
                    tool=name.value,
                    detail=(
                        f"expected {sorted(contract.required_arguments)}; "
                        f"advertised {sorted(remote.required_arguments)}"
                    ),
                )
            )
        if set(remote.argument_names) != set(contract.argument_names):
            issues.append(
                McpToolDriftIssue(
                    kind="argument_names",
                    tool=name.value,
                    detail=f"expected {sorted(contract.argument_names)}; advertised {sorted(remote.argument_names)}",
                )
            )

    return McpToolDriftReport(compatible=not issues, checked_tools=len(MCP_TOOLS), issues=tuple(issues))
