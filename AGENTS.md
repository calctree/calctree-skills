# CalcTree

CalcTree is an engineering calculation platform. A **page** holds prose plus calculation
blocks; the blocks form a calculation graph that evaluates server-side with real units. This
repo is how an AI agent drives it from outside the platform.

**Read [`skills/calctree/SKILL.md`](skills/calctree/SKILL.md) first.**
It is the verified, current account of how to create and read calculation pages, and it
supersedes any older CalcTree API documentation.

This file exists so agent tools that look for `AGENTS.md` — Cursor, Codex, and others — find
the same guidance Claude Code gets from the skill. There is nothing here that is not in the
skill; it is a pointer, not a second source of truth.

## What to read, depending on what you can run

| You can | Read |
|---|---|
| run Python | [`scripts/calctree_api.py`](skills/calctree/scripts/calctree_api.py) — standard library only, no install, has a CLI |
| only make HTTP calls | [`REFERENCE.md`](skills/calctree/REFERENCE.md) — every GraphQL document, its variables and response shape |
| neither | the skill alone still tells you the authoring rules that decide whether a generated page is correct |

## Setup

```bash
export CALCTREE_API_KEY=...      # reads and page creation only; content writes need a user token (CTP-4734)
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
