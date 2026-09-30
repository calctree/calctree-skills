# Testing the CalcTree skill

How to test the tool-use and page-building paths across surfaces and models.

## Prerequisites

1. A CalcTree API key (`CALCTREE_API_KEY`)
2. A workspace id with at least one calculation page in it (a "Simply supported beam"
   page with `span`, `load`, `M_max` is ideal — the test prompts assume it)
3. Python 3.9+ (stdlib only, no pip)

Verify the API key works before testing anything else — an invalid key returns
`"Unexpected error."` with no 401 and no mention of auth:

```bash
export CALCTREE_API_KEY=...
python3 skills/calctree/scripts/calctree_api.py pages <workspaceId>
```

## Creating a test page

If you don't have a beam page to point tool-use tests at, create one:

```bash
python3 skills/calctree/scripts/calctree_api.py build <workspaceId> "Test beam" -
```

Then paste this MDX and press Ctrl-D:

```mdx
## Inputs

<EquationBlock engine="multiline_mathjs" name="Beam inputs">
span = 8 m
load = 45 kN / m
</EquationBlock>

## Calculations

<EquationBlock engine="multiline_mathjs" name="Bending moment">
M_max = load * span^2 / 8
</EquationBlock>
```

Note the page id from the output — substitute it for `{PAGE_ID}` in the test prompts.

## Test surfaces

### Claude Code (this machine)

The skill is in this repo. Point Claude Code at the repo root:

```bash
cd calctree-skills
claude
```

Then paste any test prompt. Claude Code has shell access, so it can run
`calctree_api.py` directly.

### Claude desktop app / claude.ai

1. Build the skill package: `python3 tools/package_skill.py`
2. Upload `dist/*.zip` under **Settings > Features > Skills**
3. Enable network access for the sandbox (Settings > Features > Allow network)
4. Paste a test prompt into the chat

The desktop app can read the skill guidance but runs code in a sandbox. It needs
network access toggled on to reach `graph.calctree.com`. Provide the API key in
the prompt or set it as a project-level environment variable.

### Other LLMs (ChatGPT, Gemini, Cursor, etc.)

These can't install the skill, so give them the context directly. Two options:

**Option A: paste SKILL.md as a system prompt.** Copy the contents of
`skills/calctree/SKILL.md` into the system prompt or as a
file attachment, then paste a test prompt.

**Option B: point at the raw files.** If the LLM has web access, give it the
raw GitHub URLs:

```
Read this CalcTree skill and use it to answer my question:
https://raw.githubusercontent.com/calctree/calctree-skills/main/skills/calctree/SKILL.md

My API key is: <key>
My workspace id is: <wsId>
```

For models with code execution (ChatGPT Code Interpreter, Gemini with tools),
also attach `calctree_api.py` as a file so they can import it.

For models without code execution, they'll need to make raw HTTP calls. The
`REFERENCE.md` file has the exact GraphQL documents and wire format.

## Test prompts

Two sets of prompts, in `evals/`:

### `tool-use-prompts.jsonl` — the read/execute path (new)

Six prompts testing discover, introspect, execute, error handling. Replace
`{WORKSPACE_ID}` and `{PAGE_ID}` with real values.

| # | Tests | Key thing to watch |
|---|---|---|
| 1 | Discovery — list pages | No writes, no creation |
| 2 | Introspection — read a page's interface | Correct value parsing, input/output distinction |
| 3 | Single execution | simpleCalculate with scope overrides, value = 540 kN*m |
| 4 | Execution + engineering judgment | Reads utilisation, passes/fails correctly |
| 5 | Multiple executions | Three separate calls, comparison table |
| 6 | Error handling — wrong units | Reports the error, doesn't fabricate results |

### `calctree-write-path.jsonl` — the write path (existing)

Three prompts testing page creation, utilisation checks, Python cells. These
create real pages, so point them at a workspace you don't mind writing to.

## What to check

For every test, regardless of model:

- [ ] **Auth:** uses `x-api-key` header, not Bearer, not Basic
- [ ] **No hallucinated values:** results come from the API response, not hand-computed
- [ ] **Units preserved:** values reported with their units, not stripped to numbers
- [ ] **Errors surfaced:** if a statement errors, the model reports it rather than guessing
- [ ] **Read-only when appropriate:** tool-use prompts don't create or modify pages
- [ ] **Write path correct:** creation prompts register the page in the tree
- [ ] **Value parsing:** JSON-encoded namedValues are parsed, not echoed as raw strings

### Model-specific things to watch

| Model | What tends to go wrong |
|---|---|
| GPT-4o / ChatGPT | May ignore the SKILL.md guidance and hallucinate a REST API that doesn't exist. Check it's actually calling GraphQL |
| Gemini | May strip units from values or round aggressively. Check unit strings are preserved |
| Claude Haiku | The authoring rules in §§5–8 are prose-heavy; Haiku may skip nuances like the boolean-not-ternary rule |
| Claude Sonnet/Opus | Should follow the skill well; watch for over-engineering (creating pages when asked to execute) |
| Cursor/Windsurf | Has shell access — should use `calctree_api.py` directly. Check it finds the script |

## Clean up

Every write-path test creates real pages. Clean up after:

```bash
python3 skills/calctree/scripts/calctree_api.py delete <workspaceId> <pageId>
```

This is a soft delete: pages still show in `pages` queries, and the page's node stays in the
page tree without reaching the app's Trash. To remove test pages from the sidebar cleanly, move
them into a folder and delete the folder (SKILL.md § 13).
