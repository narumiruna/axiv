---
name: using-axiv-cli
description: Use when discovering or reading alphaXiv papers, asking questions against paper PDFs, exploring paper-linked GitHub code, or listing and managing an authenticated alphaXiv personal library through the axiv CLI.
---

# Using axiv CLI

Use only the published `axiv` CLI commands in this repository.

Use an installed `axiv` executable when available.

From this source checkout, fall back to `uv run axiv` as the command prefix when `axiv` is not installed.

Read [references/installation.md](references/installation.md) when neither command prefix can show CLI help.

Stop and report the installation error when the installation instructions do not produce a working command prefix.

Do not call alphaXiv REST or MCP endpoints directly and do not import private Python client methods.

Run the resolved command prefix with `auth status --json` before any authenticated research or library workflow.

Stop and report the error when the API key is missing, authentication fails, the tool contract drifts, or alphaXiv returns `403`.

Read [references/command-map.md](references/command-map.md) to select the exact command and understand its authentication, quota, and remote effects.

Prefer `--json` whenever another tool or agent will consume the result.

Preserve the user's question and keywords instead of silently expanding acronyms or inventing search terms.

Tell the user that discover, content, query, and code commands consume Assistant quota before calling one unless their request already clearly authorizes that research action.

Stop and report quota exhaustion instead of retrying or substituting another quota-consuming command.

Use `axiv library list --json` to obtain current opaque folder IDs before planning a library change.

Before every remote library write, state the exact CLI operation, folder IDs or names, and paper IDs or URLs that will change.

Obtain explicit user authorization for those exact targets before adding `--yes`.

Treat `--yes` only as CLI confirmation and never as evidence that the user authorized the write.

Do not combine separately authorized writes or broaden a target after authorization.

For folder deletion, explicitly state that folder memberships will be removed before requesting authorization.

Stop when a write target is missing, ambiguous, destructive intent is unclear, or authorization does not match the final command.

Read [references/workflows.md](references/workflows.md) when coordinating literature review, paper analysis, PDF evidence, code verification, or library organization.

Verify success from the command's JSON result and report partial or failed outcomes without automatically retrying writes.
