# Contributing

## Release testing

Four things have to hold: it installs, it runs on a clean machine, a model actually uses it
correctly, and nothing secret ships. Work top to bottom — each stage assumes the one above
passed.

### 1. Clean machine

The point of the Python rewrite is that this needs nothing but `python3`. Prove it somewhere
with no Node, no `pip install`, and no other CalcTree checkout.

```bash
export CALCTREE_API_KEY=...
python3 skills/calctree/examples/smoke_two_page.py <workspaceId>
```

Passes when: two page URLs print, `M_max = 360`, titles report `verified=True`, and page B
shows the reference snapshot of page A's values. Needs `python3` (3.9 is the oldest tested) and
network egress to `graph.calctree.com` and `api.calctree.com`.

Then the CLI path, which is how an agent with only a shell drives it:

```bash
python3 skills/calctree/scripts/calctree_api.py build <workspaceId> "Test" page.mdx
python3 skills/calctree/scripts/calctree_api.py context <workspaceId> <pageId>
```

### 2. Install, per surface

| Surface | How | Passes when |
|---|---|---|
| Claude Code, plugin | `/plugin marketplace add .` then `/plugin install calctree@calctree` | the skill triggers on a CalcTree request. **Untested — the `"source": "./"` layout has never been verified** |
| Claude Code, manual | copy the skill folder into `~/.claude/skills/` | same |
| claude.ai, desktop, Cowork | `python3 tools/package_skill.py`, upload `dist/*.zip` under Settings > Features | upload accepted (rejects files loose at the zip root), and a write succeeds — needs network access enabled for the sandbox |
| Claude API | the same zip via `POST /v1/skills` | guidance loads. Writes **cannot** work there: that sandbox has no network |
| Cursor, Codex, other agent tools | point them at `AGENTS.md` | they follow it to `SKILL.md` and drive the API |

### 3. Behaviour

Run the scenarios in `evals/calctree-write-path.jsonl` and judge each against
its `expected_behavior`. Then check the specific traps that have actually caused bad pages:

- **Statement titles report `verified=True`.** The retry is load-bearing — roughly one run in
  three needs a second attempt, and the failure mode is a page that looks fine and is
  permanently untitled.
- **A bad key gives the translated error**, not a bare `"Unexpected error."`
- **The page is registered in the tree** — visible in the UI, not orphaned.
- **Reads settle** — no zero-statement reads straight after a write.
- **Units flow** — values carry their unit; no unit written into a column heading, no value
  stripped to a bare number.
- **No unit-conversion constant** (`/1714`, `/5252`, `449*`) on a unitful value: ask for pump
  horsepower from psi and gpm and expect `(p_d * Q_flow) to hp`.
- **A pass/fail check is a named boolean**, never a string ternary.
- **`<` and `>` are escaped** in prose as well as in formulas.
- **Variables do not collide with unit abbreviations** (`M_max`, not `M`).
- **A template reference resolves**: `insertMDXContent` returns empty `warnings`, and the
  `codeTitle.*` values downstream are non-null.

### 4. Models

Test with Haiku, Sonnet and Opus. Only Opus has driven this so far. The authoring rules in
sections 5–8 of the skill are prose-heavy, so Haiku is where thin guidance will show first.

### 5. Secrets and hygiene

- No live credential anywhere in the tree or in history. A key was previously committed and has
  been rotated; check again before publishing.
- No `.env`, no `.claude/settings.local.json`, no `dist/`.
- `LICENSE` present, and `plugin.json` records it.

### 6. Clean up after yourself

Every test above writes real pages. Deleting one is a **soft** delete, so they keep coming back
from the `pages` query and accumulate:

```bash
python3 .../calctree_api.py audit <workspaceId> <pageId>...   # find untitled statements
python3 .../calctree_api.py delete <workspaceId> <pageId>     # soft delete
```

### Known gaps at time of writing

The plugin install path is unverified, and only Opus has been tested.

## Status

This repo replaced an earlier set of API docs that had drifted for nine months. The previous
content was removed rather than edited, because its quick start taught an authentication
path that silently dropped formulas. It remains in git history.
