# CalcTree

CalcTree is an engineering calculation platform. A **page** holds prose plus calculation
blocks; the blocks form a calculation graph that evaluates server-side with real units. This
repo is how an AI agent drives it from outside the platform.

## Use the MCP server first

If the CalcTree MCP server is connected (tools named `whoami`, `get_page`,
`run_calculation`), use it to find, read and run pages. Do not drive the GraphQL API by hand
for that.

- URL: `https://mcp.calctree.com/mcp` (Streamable HTTP).
- Auth: sign in with a CalcTree account (OAuth), or send an API key as
  `Authorization: Bearer <key>`.
- Tools: `whoami`, `list_workspaces`, `search_workspace`, `get_page`, `run_calculation`,
  `list_templates`, `create_pdf_report`, `guide`. Call `guide` before you write or interpret
  page content.
- It cannot write page content yet. To build pages, follow the skill below.
- Not connected? Claude Code: `claude mcp add --transport http calctree
  https://mcp.calctree.com/mcp`. Cursor and other clients: add a remote MCP server with that
  URL (steps at [docs.calctree.com](https://docs.calctree.com), "Connect your AI to
  CalcTree").

## Building pages and the skill

**Read [`skills/calctree/SKILL.md`](skills/calctree/SKILL.md) for anything that writes.**
It is the verified, current account of how to create and read calculation pages, and it
supersedes any older CalcTree API documentation.

This file exists so agent tools that look for `AGENTS.md` — Cursor, Codex, and others — find
the same guidance Claude Code gets from the skill. There is nothing here that is not in the
skill; it is a pointer, not a second source of truth.

## What to read, depending on what you can run (the scripts are deprecated)

The Python scripts and the raw GraphQL path predate the MCP server. They remain only for
writing pages, until the MCP server can, and will be removed after a release or two.

| You can | Read |
|---|---|
| run Python | [`scripts/calctree_api.py`](skills/calctree/scripts/calctree_api.py) — standard library only, no install, has a CLI |
| only make HTTP calls | [`REFERENCE.md`](skills/calctree/REFERENCE.md) — every GraphQL document, its variables and response shape |
| neither | the skill alone still tells you the authoring rules that decide whether a generated page is correct |

## Setup

```bash
export CALCTREE_API_KEY=...      # reads and page creation only (CTP-4734)
export CALCTREE_ACCESS_TOKEN=... # user token: needed to write page content
python3 skills/calctree/examples/smoke_two_page.py <workspaceId>
```

The smoke test writes two real pages, so point it at a workspace you do not mind writing to.

## The five things that catch everyone out

1. **A page must be registered in the page tree.** `createPageSync` then `addPageNode`. A page
   that exists but is not in the tree is orphaned and invisible.
2. **Evaluation is asynchronous.** Settle a couple of seconds after a write before reading, or
   the read returns zero statements.
3. **Verify with the `calculation` query, never by reading the page back as MDX.** MDX
   round-trips prose but returns calculation blocks empty, so a correct page looks broken.
4. **Check `statementsCreated`, not the HTTP status.** A write that inserted nodes and created
   no statements is a failure that returns 200.
5. **An invalid API key does not say so.** It comes back as a bare GraphQL
   `"Unexpected error."` with no 401 and no mention of auth.
