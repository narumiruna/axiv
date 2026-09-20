import pytest
from pydantic import ValidationError

from axiv.clients.mcp import McpClient
from axiv.contracts.mcp import MCP_TOOLS
from axiv.contracts.mcp import McpAccess
from axiv.contracts.mcp import McpQuota
from axiv.contracts.mcp import McpToolName
from axiv.models.mcp import DiscoverPapersArguments


def test_static_mcp_contracts_cover_exact_official_tool_surface() -> None:
    assert set(MCP_TOOLS) == set(McpToolName)
    assert len(MCP_TOOLS) == 11
    assert sum(contract.access is McpAccess.WRITE for contract in MCP_TOOLS.values()) == 6
    assert sum(contract.quota is McpQuota.ASSISTANT for contract in MCP_TOOLS.values()) == 4
    assert all(contract.model_config.get("frozen") for contract in MCP_TOOLS.values())


def test_contracts_derive_required_fields_from_aliased_argument_schemas() -> None:
    discover = MCP_TOOLS[McpToolName.DISCOVER_PAPERS]

    assert discover.arguments_model is DiscoverPapersArguments
    assert discover.required_arguments == ("keywords", "question", "difficulty")
    assert MCP_TOOLS[McpToolName.READ_GITHUB_FILES].required_arguments == ("githubUrl", "path")
    for contract in MCP_TOOLS.values():
        schema = contract.arguments_model.model_json_schema(by_alias=True)
        assert contract.required_arguments == tuple(schema.get("required", ()))
    with pytest.raises(ValidationError):
        discover.arguments_model.model_validate({"question": "missing required fields"})


@pytest.mark.parametrize(
    ("name", "required"),
    [
        (McpToolName.DISCOVER_PAPERS, ("keywords", "question", "difficulty")),
        (McpToolName.GET_PAPER_CONTENT, ("url",)),
        (McpToolName.ANSWER_PDF_QUERIES, ("paper", "queries")),
        (McpToolName.READ_GITHUB_FILES, ("githubUrl", "path")),
        (McpToolName.LIST_LIBRARY, ()),
        (McpToolName.SAVE_PAPERS, ("paper_ids_or_urls",)),
        (McpToolName.REMOVE_PAPERS, ("paper_ids_or_urls", "folder_id")),
        (McpToolName.MOVE_PAPERS, ("paper_ids_or_urls", "from_folder_id", "to_folder_id")),
        (McpToolName.CREATE_FOLDER, ("name",)),
        (McpToolName.RENAME_FOLDER, ("folder_id", "name")),
        (McpToolName.DELETE_FOLDER, ("folder_id",)),
    ],
)
def test_reviewed_required_argument_sets_remain_unchanged(name, required):
    assert MCP_TOOLS[name].required_arguments == required


def test_public_client_has_no_arbitrary_tool_or_endpoint_entrypoint() -> None:
    assert not hasattr(McpClient, "call_tool")
    assert not hasattr(McpClient, "request")
    assert not hasattr(McpClient, "base_url")
