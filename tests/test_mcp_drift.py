from axiv.contracts.mcp import MCP_TOOLS
from axiv.contracts.mcp import check_mcp_tools
from axiv.models.mcp import McpToolDescription
from axiv.models.mcp import McpToolList


def compatible_tools() -> McpToolList:
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


def test_tools_list_matches_static_contracts() -> None:
    report = check_mcp_tools(compatible_tools())

    assert report.compatible is True
    assert report.checked_tools == 11
    assert report.issues == ()


def test_additive_unreviewed_tools_do_not_break_static_contracts_or_register_calls() -> None:
    tools = compatible_tools()
    changed = McpToolList(
        tools=(*tools.tools, McpToolDescription(name="future_tool", required_arguments=(), argument_names=()))
    )

    report = check_mcp_tools(changed)

    assert report.compatible is True
    assert report.issues == ()
    assert len(MCP_TOOLS) == 11


def test_drift_reports_missing_reviewed_tools() -> None:
    tools = compatible_tools()

    report = check_mcp_tools(McpToolList(tools=tools.tools[1:]))

    assert report.compatible is False
    assert {issue.kind for issue in report.issues} == {"missing_tool"}


def test_drift_reports_required_and_property_changes() -> None:
    tools = compatible_tools()
    first = tools.tools[0]
    changed_first = McpToolDescription(
        name=first.name,
        required_arguments=(*first.required_arguments, "new_required"),
        argument_names=(*first.argument_names, "new_optional"),
    )

    report = check_mcp_tools(McpToolList(tools=(changed_first, *tools.tools[1:])))

    assert report.compatible is False
    assert {issue.kind for issue in report.issues} == {"required_arguments", "argument_names"}
    details = {issue.kind: issue.detail for issue in report.issues}
    assert details["required_arguments"] == (
        f"expected {sorted(first.required_arguments)}; advertised {sorted(changed_first.required_arguments)}"
    )
    assert details["argument_names"] == (
        f"expected {sorted(first.argument_names)}; advertised {sorted(changed_first.argument_names)}"
    )
