#!/usr/bin/env python3
"""
Two-page smoke test. Run this first to confirm your key and endpoint work end to end:

  1. create page A (registered in the tree) with inputs and a derived result
  2. read A back and confirm it evaluated server-side
  3. create page B
  4. reference A into B — a snapshot of A's computed values
  5. read B back and print both /edit URLs

It creates two real pages, so point it at a workspace you do not mind writing to.

Usage: CALCTREE_ACCESS_TOKEN=... python3 examples/smoke_two_page.py <workspaceId>
(An API key alone cannot write content, CTP-4734, so this needs the access token.)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from calctree_api import (  # noqa: E402
    CalcTreeError, create_page_in_tree, get_page_context, insert_mdx_content,
    apply_mdx_statement_titles, page_url, reference_page_via_api,
)

MDX_A = """Simply-supported beam: a UDL over a clear span, mid-span moment.

<EquationBlock name="Beam moment">
```
span = 8 m
load = 45 kN / m
M_max = load * span^2 / 8
```
</EquationBlock>
"""


def fmt(raw) -> str:
    v = raw
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except (ValueError, TypeError):
            return str(raw)
    if isinstance(v, dict) and v.get("mathjs") == "Unit":
        val = v.get("value")
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        return f"{val} {v.get('unit')}"
    return json.dumps(v, separators=(",", ":"))


def show(label: str, ctx: dict) -> None:
    print(f"  {label}: {len(ctx['statements'])} statement(s)")
    for s in ctx["statements"]:
        vals = ", ".join(f"{nv['name']}={fmt(nv.get('value'))}"
                         for nv in (s.get("namedValues") or []) if nv.get("name"))
        errs = f"  ERRORS: {s['errors']}" if s.get("errors") else ""
        formula = (s.get("formula") or "").replace("\n", " ")
        print(f"    [{s['engine']}] {s.get('title')!r} {formula}")
        print(f"      => {vals or '(no value yet)'}{errs}")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python3 examples/smoke_two_page.py <workspaceId>", file=sys.stderr)
        return 2
    ws = sys.argv[1]
    if not os.environ.get("CALCTREE_ACCESS_TOKEN"):
        # Refuse before creating anything: with a key alone, page creation succeeds and
        # the content write then fails (CTP-4734), leaving an empty page behind.
        print("set CALCTREE_ACCESS_TOKEN: an API key cannot write page content "
              "(CTP-4734). See REFERENCE.md, 'Writing content: use a user token'.",
              file=sys.stderr)
        return 2
    print("using CALCTREE_ACCESS_TOKEN\n")

    # 1. page A, with a formula that has to evaluate server-side
    a = create_page_in_tree(ws, "Smoke A - inputs")
    print(f"created A: {page_url(ws, a['id'])}")
    ins = insert_mdx_content(ws, a["id"], MDX_A)
    print(f"  insertMDXContent: {ins['insertedCount']} nodes, "
          f"{ins['statementsCreated']} statement(s)")
    if ins["statementsCreated"] == 0 and ins["insertedCount"] > 0:
        print("  FAILED: nodes inserted but no statements created — the page will not "
              "compute. Check CALCTREE_ACCESS_TOKEN.", file=sys.stderr)
        return 1

    titles = apply_mdx_statement_titles(ws, a["id"], MDX_A)
    print(f"  titles: {titles['titled']} set, verified={titles['verified']}, "
          f"attempts={titles['attempts']}")
    if not titles["verified"]:
        print("  WARNING: statement titles were not confirmed on the page", file=sys.stderr)

    # 2. read A back — evaluation is async, so settle first
    time.sleep(2)
    show("page A", get_page_context(ws, a["id"]))
    print()

    # 3 + 4. page B, referencing A rather than recomputing it
    b = create_page_in_tree(ws, "Smoke B - references A")
    print(f"created B: {page_url(ws, b['id'])}")
    ref = reference_page_via_api(ws, b["id"], a["id"])
    print(f"  reference: alias={ref['alias']!r}, {ref['count']} value(s) snapshotted")

    # 5. read B back
    time.sleep(2)
    show("page B", get_page_context(ws, b["id"]))

    print("\nDONE.")
    print(f"  A: {page_url(ws, a['id'])}")
    print(f"  B: {page_url(ws, b['id'])}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CalcTreeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
