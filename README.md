# calctree-skills

Turn engineering calculations into AI-callable tools with
[CalcTree](https://www.calctree.com). A CalcTree **page** is a calculation graph that
evaluates server-side with real units. Connect the **CalcTree MCP server** and your AI can
find pages in a workspace and run them with custom inputs. This repo's skill adds the
authoring rules and the page-building path.

## Connect the MCP server

```
https://mcp.calctree.com/mcp
```

Sign in with your CalcTree account (OAuth), or send an API key as
`Authorization: Bearer <key>`. Tools: `whoami`, `list_workspaces`, `search_workspace`,
`get_page`, `run_calculation`, `list_templates`, `create_pdf_report`, `guide`. It finds, reads
and runs pages and exports PDFs. It cannot write page content yet, so building pages still
follows the skill.

Claude Code, one command:

```bash
claude mcp add --transport http calctree https://mcp.calctree.com/mcp
```

Or install the plugin below, which adds the server and the skill together. Steps for
Claude.ai, Claude Desktop, Cursor and ChatGPT are in
[Connect your AI to CalcTree](https://docs.calctree.com).

## Layout

```
skills/calctree/
  SKILL.md                    the skill: read this first
  VERSION                     the skill's version, shipped in the zip
  REFERENCE.md                every GraphQL document, for driving it without our code
  scripts/calctree_api.py     the primitives: stdlib only, importable and a CLI (deprecated)
  examples/smoke_two_page.py  end-to-end example (deprecated)
tools/package_skill.py        builds the distributable zip
.claude-plugin/               Claude Code plugin + marketplace manifests
.mcp.json                     the MCP server the plugin connects (mcp.calctree.com)
AGENTS.md                     entry point for agent tools that look for it
evals/                        evaluation scenarios
llms.txt                      machine-readable index
CHANGELOG.md                  what changed in each release
CONTRIBUTING.md               versioning and release testing
```


## Quick start without the MCP server (deprecated)

The Python scripts below predate the MCP server and are **deprecated**. Use the MCP server
to find and run pages. They stay for now because the MCP server cannot write page content
yet, and will be removed after a release or two once it can.

```bash
export CALCTREE_API_KEY=...
python3 skills/calctree/scripts/calctree_api.py pages <workspaceId>
python3 skills/calctree/scripts/calctree_api.py execute <workspaceId> <pageId> span="10 m"
```

No install: standard library only, no pip, no Node. An API key covers reads and page
creation, but not writing page content (CTP-4734). To write, set `CALCTREE_ACCESS_TOKEN`
to a user access token (`REFERENCE.md`, "Writing content: use a user token"). The smoke
test needs the token, refuses to start without it, and creates two real pages, so point
it at a workspace you do not mind writing to:

```bash
CALCTREE_ACCESS_TOKEN=... python3 skills/calctree/examples/smoke_two_page.py <workspaceId>
```

## Installing it

| Surface | How |
|---|---|
| Claude Code | `/plugin marketplace add calctree/calctree-skills` then `/plugin install calctree@calctree`: adds the skill and connects the MCP server (run `/mcp` and authenticate). Or copy the skill folder into `~/.claude/skills/` and run `claude mcp add --transport http calctree https://mcp.calctree.com/mcp` |
| claude.ai, desktop, Cowork | add the MCP server as a connector (Settings > Connectors, URL above). For the skill, download [calctree.zip](https://github.com/calctree/calctree-skills/releases/latest/download/calctree.zip) (or build it with `python3 tools/package_skill.py`), then upload it under Settings > Features |
| Claude API | the same zip via `POST /v1/skills`. Note that surface has no network access, so only the guidance is usable there, not the write path |
| Cursor, Codex, other agent tools | add the MCP server (docs link above), and point them at `AGENTS.md` |

Network access is required for everything except reading the guidance. On claude.ai, Free/Pro/Max
users toggle it in settings; Team and Enterprise admins allowlist `graph.calctree.com`.

Four things that catch everyone out, all covered in the skill:

1. **Dataset variables (VLOOKUP) are not in the `simpleCalculate` scope.** Pages that rely
   on VLOOKUP cannot be fully executed via the tool-use API path.
2. **A page must be registered in the page tree.** A page that exists but is not in the tree
   is orphaned and invisible.
3. **Evaluation is asynchronous.** Settle about two seconds after a write before reading, or
   you may read zero statements.
4. **An invalid API key does not say so.** It comes back as a GraphQL `"Unexpected error."`
   with no 401 and no mention of auth.

## Updates

Each version is a numbered GitHub release, listed in [CHANGELOG.md](CHANGELOG.md). The
download link above always points at the newest one. To be told about new versions, use
**Watch > Custom > Releases** on this repo. In Claude Code, `/plugin marketplace update
calctree` pulls the latest. The skill also checks for a newer version itself, once per
conversation, when it already has network access.

## Contributing

Release testing — clean-machine, per-surface install, behaviour and model checks — is in
[CONTRIBUTING.md](CONTRIBUTING.md). Run it before cutting a release.

## Licence

MIT. See [LICENSE](LICENSE).
