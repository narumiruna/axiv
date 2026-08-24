import re
from pathlib import Path

from typer.main import get_command

from axiv.cli import app

SKILL_DIR = Path(__file__).parents[1] / "skills" / "using-axiv-cli"
SKILL_FILE = SKILL_DIR / "SKILL.md"


def registered_commands() -> set[tuple[str, ...]]:
    root = get_command(app)
    commands: set[tuple[str, ...]] = set()

    def walk(command: object, prefix: tuple[str, ...]) -> None:
        children = getattr(command, "commands", None)
        if not isinstance(children, dict):
            commands.add(prefix)
            return
        for name, child in children.items():
            walk(child, (*prefix, name))

    walk(root, ())
    return commands


def frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    return dict(line.split(":", 1) for line in block.splitlines())


def test_skill_name_frontmatter_and_required_references() -> None:
    metadata = frontmatter(SKILL_FILE.read_text())

    assert metadata["name"].strip() == SKILL_DIR.name
    assert "alphaXiv" in metadata["description"]
    assert (SKILL_DIR / "references" / "installation.md").is_file()
    assert (SKILL_DIR / "references" / "command-map.md").is_file()
    assert (SKILL_DIR / "references" / "workflows.md").is_file()


def test_skill_relative_links_resolve() -> None:
    for source in SKILL_DIR.rglob("*.md"):
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", source.read_text()):
            if "://" not in target:
                assert (source.parent / target).resolve().is_file(), f"broken link in {source}: {target}"


def test_skill_prose_uses_one_sentence_per_line() -> None:
    for source in SKILL_DIR.rglob("*.md"):
        in_frontmatter = False
        for line in source.read_text().splitlines():
            if line == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter or not line or line.startswith(("#", "|", "```")):
                continue
            assert line.endswith((".", "。", ":")), f"non-sentence line in {source}: {line}"
            endings = r"[.!?\u3002\uff01\uff1f](?:\s|$)"
            assert len(re.findall(endings, line)) == 1, f"multiple sentences in {source}: {line}"


def test_command_map_references_only_registered_cli_commands() -> None:
    command_map = (SKILL_DIR / "references" / "command-map.md").read_text()
    referenced: set[tuple[str, ...]] = set()
    for invocation in re.findall(r"`(axiv [^`]+)`", command_map):
        path = []
        for token in invocation.split()[1:]:
            if token.startswith("-") or token[:1].isupper():
                break
            path.append(token)
        referenced.add(tuple(path))

    assert referenced
    assert referenced <= registered_commands()


def test_skill_uses_only_cli_and_contains_required_safety_stops() -> None:
    combined = "\n".join(path.read_text() for path in SKILL_DIR.rglob("*.md"))

    assert "https://api.alphaxiv.org" not in combined
    assert "McpClient" not in combined
    assert "PublicRestClient" not in combined
    for required in ("--yes", "quota", "403", "breaking tool drift", "explicit user authorization"):
        assert required.lower() in combined.lower()
    assert "unexpected runtime, MCP connection, initialization, or breaking tool drift error" in combined
    assert "handles streamable HTTP to SSE fallback only before tool dispatch" in combined
    assert "Do not automatically retry a quota-consuming command or remote library write after updating" in combined
    assert "Never invoke `mcp2cli` or another generic MCP client as a fallback" in combined
