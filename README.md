# calctree-skills

Turn engineering calculations into AI-callable tools with
[CalcTree](https://www.calctree.com). A CalcTree **page** is a calculation graph that
evaluates server-side with real units. This repo gives your AI the skill to discover pages
in a workspace, execute them with custom inputs, and build new ones.

## Layout

```
skills/calctree/
  SKILL.md                    the skill: read this first
  REFERENCE.md                every GraphQL document, for driving it without our code
  scripts/calctree_api.py     the primitives: stdlib only, importable and a CLI
  examples/smoke_two_page.py  end-to-end example
tools/package_skill.py        builds the distributable zip
.claude-plugin/               Claude Code plugin + marketplace manifests
AGENTS.md                     entry point for agent tools that look for it
evals/                        evaluation scenarios
llms.txt                      machine-readable index
CONTRIBUTING.md               release testing
```


## Quick start: use a page as a tool

```bash
export CALCTREE_API_KEY=...
python3 skills/calctree/scripts/calctree_api.py pages <workspaceId>
python3 skills/calctree/scripts/calctree_api.py execute <workspaceId> <pageId> span="10 m"
```

No install: standard library only, no pip, no Node. To verify writes work too, run the
smoke test (creates two real pages, so point it at a workspace you do not mind writing to):

```bash
python3 skills/calctree/examples/smoke_two_page.py <workspaceId>
```

## Installing it

| Surface | How |
|---|---|
| Claude Code | `/plugin marketplace add calctree/calctree-skills` then `/plugin install calctree@calctree`, or copy the skill folder into `~/.claude/skills/` |
| claude.ai, desktop, Cowork | `python3 tools/package_skill.py`, then upload `dist/*.zip` under Settings > Features |
| Claude API | the same zip via `POST /v1/skills`. Note that surface has no network access, so only the guidance is usable there, not the write path |
| Cursor, Codex, other agent tools | point them at `AGENTS.md` |

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

## Contributing

Release testing — clean-machine, per-surface install, behaviour and model checks — is in
[CONTRIBUTING.md](CONTRIBUTING.md). Run it before cutting a release.

## Licence

MIT. See [LICENSE](LICENSE).
