# axiv

`axiv` is a typed Python CLI for alphaXiv's reviewed public REST reads and official MCP research and library tools.

The CLI uses Typer, HTTPX, the official MCP Python SDK, and `pydantic.BaseModel`.

It does not dynamically expose OpenAPI operations, arbitrary HTTP requests, or arbitrary MCP tools and arguments.

## Install

Install `axiv` with uv.

```bash
uv tool install axiv
```

Or run it without installing.

```bash
uvx axiv --help
```

## Commands

Search public papers, extracted text, topics, and organizations.

```bash
uv run axiv search papers "transformer" --limit 5
uv run axiv search full-text "scaled dot-product attention" --limit 3
uv run axiv search topics "transformer"
uv run axiv search organizations "MIT"
```

Browse researchers, events, feeds, and topic groups.

```bash
uv run axiv researchers list --limit 5
uv run axiv researchers search "Yann LeCun" --limit 5
uv run axiv events list --limit 5
uv run axiv feed list --sort Recent --interval "7 Days" --limit 5
uv run axiv feed topics
```

Read paper metadata and existing derived data without starting remote generation jobs.

```bash
uv run axiv paper show 1706.03762
uv run axiv paper preview 1706.03762
uv run axiv paper text 1706.03762 --page 1
uv run axiv paper overview 1706.03762 --language en
uv run axiv paper related 1706.03762 --kind metrics
```

Add `--json` to any read command for stable machine-readable output.

```bash
uv run axiv search papers "transformer" --limit 1 --json
```

Search and list commands enforce conservative result limits.

The public REST client never sends `Authorization` or Cookie headers because several anonymous alphaXiv endpoints reject requests carrying an API Key.

## Authenticated MCP commands

Create an API key in alphaXiv's MCP/API settings and provide it only through the environment.

```bash
export ALPHAXIV_API_KEY="your-key"
uv run axiv auth status --json
```

The CLI does not accept `--api-key`, browser cookies, or arbitrary MCP endpoints.

The native MCP client uses streamable HTTP first and falls back to SSE only while opening or initializing a session.

It never changes transports or retries after a tool call begins.

Research commands call alphaXiv Assistant models and consume Assistant quota.

```bash
uv run axiv research discover "How do transformers use attention?" --keyword transformer --keyword attention --json
uv run axiv paper content 1706.03762 --json
uv run axiv paper query 1706.03762 --query "What datasets were used?" --json
uv run axiv paper code https://github.com/owner/repository / --json
```

Batch every question for one paper as repeated `--query` options to avoid unnecessary quota use.

Library listing is read only and does not load papers unless `--include-papers` is supplied.

```bash
uv run axiv library list --json
```

Every remote library write requires `--yes` and an exact folder and paper target.

```bash
uv run axiv library save FOLDER_ID 1706.03762 --yes --json
uv run axiv library move SOURCE_FOLDER TARGET_FOLDER 1706.03762 --yes --json
uv run axiv library folder create "Reading list" --yes --json
```

For agents, `--yes` does not replace explicit user authorization for the exact remote change.

The source skill at [`skills/using-axiv-cli/`](skills/using-axiv-cli/SKILL.md) defines safe research and library workflows.

## OpenAPI contract check

The development OpenAPI document is a development-time reference only.

Run the explicit drift check to compare the remote document with the 26 reviewed static contracts.

```bash
uv run scripts/check_openapi_contract.py
```

The checker only downloads `https://api-dev.alphaxiv.org/api.json` and reports drift.

It does not generate source code or call any API operation described by the document.

## Development

Run the same checks as CI on Python 3.12.

```bash
uv run ruff check .
uv run ty check .
uv run pytest -v -s --cov=src --cov-report=xml tests
```

Live REST smoke tests are opt-in and read only.

```bash
ALPHAXIV_LIVE=1 uv run pytest tests/e2e/test_live_rest_readonly.py -q
```

Live MCP authentication and library listing require both the read-only opt-in and an API key.

```bash
ALPHAXIV_LIVE=1 ALPHAXIV_API_KEY="your-key" uv run pytest tests/e2e/test_live_mcp_readonly.py -q
```

The one-case MCP research smoke test is separate because it consumes Assistant quota.

```bash
ALPHAXIV_LIVE_RESEARCH=1 ALPHAXIV_API_KEY="your-key" uv run pytest tests/e2e/test_live_mcp_research.py -q -s
```

See [`docs/research/alphaxiv-api.md`](docs/research/alphaxiv-api.md) for the API research and safety boundaries.
