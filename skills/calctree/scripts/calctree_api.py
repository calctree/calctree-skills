#!/usr/bin/env python3
"""
CalcTree driving primitives: pages, MDX content, calculations, page-context reads
and cross-page references, over the public GraphQL endpoint with an API key.

Standard library only — no pip install, no virtualenv, no Node. Runs anywhere
python3 exists, which includes agent sandboxes that cannot install packages.

Usable two ways:

  import:  from calctree_api import create_page_in_tree, insert_mdx_content, ...
  shell:   python3 calctree_api.py build <workspaceId> "Page title" page.mdx

Env:
  CALCTREE_API_KEY   required
  CALCTREE_GRAPH_URL optional, defaults to production

Run `python3 calctree_api.py --help` for the command list.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

GRAPH_URL = os.environ.get("CALCTREE_GRAPH_URL") or "https://graph.calctree.com/graphql"

# '~' is the platform's latest-revision sentinel (REVISION_INFINITE) and is correct
# because '~' sorts above every base62 character, so it always means "latest".
# Hex-looking values ('ffffffff') appear in older docs and answer today only because
# no revision id has yet sorted above them: a KSUID starting with a letter after 'f'
# silently stops matching. Do not go back to a hex value.
LATEST_REVISION_ID = "~"

APP_URL = "https://app.calctree.com"


class CalcTreeError(RuntimeError):
    pass


def _auth_headers() -> dict[str, str]:
    """One API key covers reads, page creation and content/calculation writes."""
    key = os.environ.get("CALCTREE_API_KEY")
    if not key:
        raise CalcTreeError("Set CALCTREE_API_KEY")
    return {"x-api-key": key}


# 90s: a content write with many statements is the slowest call here and has been
# observed taking tens of seconds; anything past this is a hang, not slowness.
GQL_TIMEOUT_S = 90


def gql(query: str, variables: dict, timeout: int = GQL_TIMEOUT_S) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        GRAPH_URL, data=body, method="POST",
        headers={"Content-Type": "application/json", **_auth_headers()},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            payload = json.loads(res.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:400].decode(errors="replace")
        raise CalcTreeError(f"HTTP {e.code} from the GraphQL endpoint: {detail}") from None
    errors = payload.get("errors")
    if errors:
        msg = "; ".join(e.get("message", "?") for e in errors)
        # An invalid or empty API key surfaces as a bare "Unexpected error." with no
        # 401 and no mention of auth, so name the likely cause instead of passing it on.
        if re.search(r"unexpected error", msg, re.I):
            raise CalcTreeError(
                f"GraphQL: {msg} — this is what an invalid or empty CALCTREE_API_KEY "
                "looks like; check the key before debugging anything else."
            )
        raise CalcTreeError(f"GraphQL: {msg}")
    if "data" not in payload:
        raise CalcTreeError("GraphQL response carried no data")
    return payload["data"]


def new_id() -> str:
    """Client-minted ids are accepted. Platform-generated ids are 21-char nanoids,
    so id shape is how you tell an API-created page from a UI-created one."""
    return str(uuid.uuid4())


def page_url(workspace_id: str, page_id: str) -> str:
    return f"{APP_URL}/edit/{workspace_id}/{page_id}"


# ---- READ ----

def list_workspace_pages(workspace_id: str) -> list[dict]:
    """Note: deleting a page is a SOFT delete, so trashed pages still come back here."""
    data = gql(
        "query($workspaceId: ID!){ pages(workspaceId: $workspaceId){ id title } }",
        {"workspaceId": workspace_id},
    )
    return data.get("pages") or []


def get_page_context(workspace_id: str, page_id: str) -> dict:
    """The way to verify a page: statements with namedValues and errors.

    Do NOT verify by reading the page back as MDX — MDX round-trips prose but
    returns calculation blocks empty, so a correct page looks broken.
    """
    page, content = None, None
    try:
        d = gql(
            """query($workspaceId: ID!, $pageId: ID!){
                 page(workspaceId: $workspaceId, id: $pageId){ id title }
                 pageContent(workspaceId: $workspaceId, pageId: $pageId){ content }
               }""",
            {"workspaceId": workspace_id, "pageId": page_id},
        )
        page = d.get("page")
        content = (d.get("pageContent") or {}).get("content")
    except CalcTreeError:
        pass

    statements = []
    try:
        d = gql(
            """query($workspaceId: ID!, $calculationId: ID!, $revisionId: ID!){
                 calculation(workspaceId: $workspaceId, calculationId: $calculationId, revisionId: $revisionId){
                   statements { statementId title engine formula namedValues { name value } errors }
                 }
               }""",
            {"workspaceId": workspace_id, "calculationId": page_id, "revisionId": LATEST_REVISION_ID},
        )
        statements = ((d.get("calculation") or {}).get("statements")) or []
    except CalcTreeError:
        pass

    return {"page": page, "content": content, "statements": statements}


def page_mdx(workspace_id: str, page_id: str) -> str | None:
    """Body back as MDX. Prose round-trips; calculation blocks come back EMPTY, so
    never use this to verify a calculation — use get_page_context."""
    d = gql(
        "query($workspaceId: ID!, $pageId: ID!){ pageMDX(workspaceId: $workspaceId, pageId: $pageId) }",
        {"workspaceId": workspace_id, "pageId": page_id},
    )
    return d.get("pageMDX")


# ---- CREATE ----

def create_page_sync(workspace_id: str, title: str, page_id: str | None = None,
                     parent_id: str | None = None) -> dict:
    pid = page_id or new_id()
    page_input = {"id": pid, "title": title, "workspaceId": workspace_id}
    if parent_id:
        page_input["parentId"] = parent_id
    d = gql(
        """mutation($workspaceId: ID!, $input: CreatePageInput!){
             createPageSync(workspaceId: $workspaceId, input: $input){ id title }
           }""",
        {"workspaceId": workspace_id, "input": page_input},
    )
    return d["createPageSync"]


def add_page_node(workspace_id: str, page_id: str, parent_id: str | None = None) -> dict:
    """REQUIRED after create_page_sync, or the page is orphaned and invisible."""
    node_input = {"pageId": page_id}
    if parent_id:
        node_input["parentId"] = parent_id
    d = gql(
        """mutation($workspaceId: ID!, $input: AddPageNodeInput!){
             addPageNode(workspaceId: $workspaceId, input: $input){ newPageId parentId }
           }""",
        {"workspaceId": workspace_id, "input": node_input},
    )
    return d["addPageNode"]


def create_page_in_tree(workspace_id: str, title: str, parent_id: str | None = None) -> dict:
    """Create a page AND register it in the page tree. Both steps are required."""
    page = create_page_sync(workspace_id, title, parent_id=parent_id)
    add_page_node(workspace_id, page["id"], parent_id=parent_id)
    return page


def create_pdf_report(
    workspace_id: str,
    page_ids: list[str],
    title: str = "Report",
    file_name: str = "report",
) -> dict:
    """Create a PDF report and poll until ready. Returns {id, signedUrl, fileSize}."""
    import time

    d = gql(
        """mutation($workspaceId: ID!, $input: CreatePdfReportInput!) {
          createPdfReport(workspaceId: $workspaceId, input: $input) {
            id reportStatus
          }
        }""",
        {
            "workspaceId": workspace_id,
            "input": {
                "pageIds": page_ids,
                "title": title,
                "fileName": file_name,
                "settings": {
                    "paperSize": "A4",
                    "orientation": "portrait",
                    "includeTitlePage": True,
                    "includeTableOfContents": True,
                    "showPageNumbers": True,
                    "pageNumberPosition": "bottom-center",
                },
                "highlightCalcItems": True,
                "mathNotation": True,
                "unitSystem": "si",
            },
        },
    )
    report_id = d["createPdfReport"]["id"]
    for _ in range(60):
        time.sleep(4)
        q = gql(
            """query($workspaceId: ID!, $id: ID!) {
              pdfReport(workspaceId: $workspaceId, id: $id) {
                reportStatus errorMessage fileSize signedUrl
              }
            }""",
            {"workspaceId": workspace_id, "id": report_id},
        )
        r = q["pdfReport"]
        if r["reportStatus"] == "ready":
            return {"id": report_id, "signedUrl": r["signedUrl"], "fileSize": r["fileSize"]}
        if r["reportStatus"] == "error":
            raise CalcTreeError(f"PDF generation failed: {r['errorMessage']}")
    raise CalcTreeError("PDF generation timed out after 4 minutes")


def delete_page(workspace_id: str, page_id: str) -> None:
    """Soft delete: the page still comes back from list_workspace_pages."""
    gql(
        "mutation($workspaceId: ID!, $id: ID!){ deletePage(workspaceId: $workspaceId, id: $id){ id } }",
        {"workspaceId": workspace_id, "id": page_id},
    )


# ---- CONTENT ----

def put_initial_page_content(workspace_id: str, page_id: str, mdx: str) -> None:
    gql(
        """mutation($workspaceId: ID!, $input: PutPageContentInput!){
             putInitialPageContent(workspaceId: $workspaceId, input: $input)
           }""",
        {"workspaceId": workspace_id, "input": {"pageId": page_id, "content": mdx}},
    )


def insert_mdx_content(workspace_id: str, page_id: str, mdx: str,
                       position: dict | None = None) -> dict:
    """Prose and calculation blocks both go through here, and the statements DO
    evaluate server-side — a separate create_or_update_calculation is not needed to
    make a page compute. Statement titles from the MDX `name` attribute are now set
    automatically (fixed on prod 2026-08-24).

    Returns {insertedCount, statementsCreated, warnings}. ALWAYS check
    statementsCreated against the number of blocks you sent: a write that
    persisted nothing is a failure whatever the HTTP status said. `warnings` lists
    what was skipped, currently <PageReference> tags the server refused (template
    not visible, never published, unknown version); it must be empty.

    `position` is a Slate location; the default prepends at [0]. To append, pass
    {"path": [<current top-level node count>]}.
    """
    d = gql(
        """mutation($workspaceId: ID!, $pageId: ID!, $content: String!, $position: LocationInput!){
             insertMDXContent(workspaceId: $workspaceId, pageId: $pageId, content: $content, position: $position){
               insertedCount statementsCreated warnings
             }
           }""",
        {"workspaceId": workspace_id, "pageId": page_id, "content": mdx,
         "position": position or {"path": [0]}},
    )
    return d["insertMDXContent"]


# ---- TEMPLATES ----

def list_templates(workspace_id: str, keywords: list[str] | None = None) -> list[dict]:
    """Every template this workspace can see (its own plus built-ins, deleted ones
    excluded), optionally filtered client-side: a template matches when every
    keyword appears in its name, description or tags. There is no server-side
    search. Pages until an EMPTY page comes back: `first` is capped at 100
    server-side, so a short page is not the end.

    A template with latestVersionId None has never been published and cannot be
    referenced with <PageReference> through the API.
    """
    out: list[dict] = []
    after = None
    while True:
        d = gql(
            """query($workspaceId: ID!, $first: Int, $after: ID){
                 workspaceTemplates(workspaceId: $workspaceId, first: $first, after: $after){
                   id name description tags source sourceId latestVersionId
                   workspace { id }
                 }
               }""",
            {"workspaceId": workspace_id, "first": 100, "after": after},
        )
        rows = d["workspaceTemplates"] or []
        if not rows:
            break
        out.extend(rows)
        after = rows[-1]["id"]
    if keywords:
        kws = [k.lower() for k in keywords]

        def hay(t: dict) -> str:
            return " ".join([t.get("name") or "", t.get("description") or "",
                             " ".join(t.get("tags") or [])]).lower()
        out = [t for t in out if all(k in hay(t) for k in kws)]
    return out


def page_templates(workspace_id: str, page_id: str) -> list[dict]:
    """Templates saved from a page, each with its latest published version number.
    How a caller that knows only a page id finds the templateId a <PageReference>
    needs. latestVersion None means never published: not referenceable via API."""
    d = gql(
        """query($workspaceId: ID!, $pageId: ID!){
             pageTemplates(workspaceId: $workspaceId, pageId: $pageId){
               templateId name latestVersion latestVersionId workspace { id }
             }
           }""",
        {"workspaceId": workspace_id, "pageId": page_id},
    )
    return d["pageTemplates"] or []


def get_template_version(workspace_id: str, version_id: str) -> dict | None:
    """One published version: its MDX `content` (what you copy) and the
    calculationId/revisionId a reference pins (read them with the calculation
    query to learn the template's input names)."""
    d = gql(
        """query($workspaceId: ID!, $id: ID!){
             workspaceTemplateVersion(workspaceId: $workspaceId, id: $id){
               id templateId version nameAtPublish calculationId revisionId content
             }
           }""",
        {"workspaceId": workspace_id, "id": version_id},
    )
    return d["workspaceTemplateVersion"]


# ---- CALCULATIONS ----

def create_or_update_calculation(workspace_id: str, page_id: str,
                                 statements: list[dict]) -> dict:
    """Write the calculation graph only, with no page body. The calculation id
    equals the page id. Each statement is {statementId?, title, engine, formula};
    engine is one of mathjs, multiline_mathjs, python, excel, dataset, connection.

    Unlike insert_mdx_content, this DOES set titles.
    """
    with_statements = [
        {
            "statementId": s.get("statementId") or new_id(),
            "formula": s["formula"],
            "title": s["title"],
            "engine": s["engine"],
        }
        for s in statements
    ]
    d = gql(
        """mutation($workspaceId: ID!, $calculationId: ID!, $withStatements: [CreateStatementInput!]!){
             createOrUpdateCalculation(workspaceId: $workspaceId, calculationId: $calculationId, withStatements: $withStatements){
               calculationId revisionId
             }
           }""",
        {"workspaceId": workspace_id, "calculationId": page_id, "withStatements": with_statements},
    )
    return d["createOrUpdateCalculation"]


def _js_number(n) -> str:
    """Match JS String(n): 8 not 8.0."""
    if isinstance(n, bool):
        return "true" if n else "false"
    if isinstance(n, float) and n.is_integer():
        return str(int(n))
    return str(n)


def value_to_mathjs_source(raw) -> str:
    """A namedValue from get_page_context arrives JSON-encoded; turn it back into
    mathjs source so downstream formulas can consume it (Unit -> "8 m")."""
    v = raw
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except (ValueError, TypeError):
            return json.dumps(raw)
    if isinstance(v, dict) and v.get("mathjs") == "Unit":
        return f"{_js_number(v.get('value'))} {v.get('unit')}"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return _js_number(v)
    return json.dumps(v, separators=(",", ":"))


def _iso_now() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{now.microsecond // 1000:03d}Z"


def reference_page_via_api(workspace_id: str, target_page_id: str,
                           source_page_id: str, alias: str | None = None) -> dict:
    """Cross-page reference: a point-in-time snapshot of the source page's computed
    values, written onto the target as a multiline_mathjs object.

    The "__ct_meta" key is what promotes it into a real source-linked page
    reference rather than a plain block. Summary and roll-up pages should
    reference upstream results this way, not recompute them.
    """
    src = get_page_context(workspace_id, source_page_id)
    title = (src.get("page") or {}).get("title") or "page"
    # alias derivation matches the frontend: every non-word char becomes '_'
    a = alias or re.sub(r"\W", "_", title)
    entries = [
        f"  {json.dumps(nv['name'])}: {value_to_mathjs_source(nv.get('value'))}"
        for s in src["statements"] for nv in (s.get("namedValues") or []) if nv.get("name")
    ]
    meta = {
        "sourcePageId": source_page_id,
        "sourcePageTitle": title,
        "sourceWorkspaceId": workspace_id,
        "importedAt": _iso_now(),
    }
    count = len(entries)
    entries.append(f'  "__ct_meta": {json.dumps(meta, separators=(",", ":"))}')
    formula = "%s = {\n%s\n}" % (a, ",\n".join(entries))
    statement_id = new_id()
    create_or_update_calculation(workspace_id, target_page_id, [
        {"statementId": statement_id, "title": f"Page: {a}",
         "formula": formula, "engine": "multiline_mathjs"},
    ])
    return {"alias": a, "statementId": statement_id, "count": count}


# ---- EXECUTE (run a page's calc graph with custom inputs) ----

def simple_calculate(workspace_id: str, calculation_id: str,
                     scope: list[dict] | None = None) -> dict:
    """Execute a page's calculation graph with optional input overrides. This is the
    read-only "use a page as a tool" call: it evaluates the full graph, substituting
    any named values you pass in ``scope``, and returns every statement's recomputed
    ``namedValues`` plus errors/warnings.

    ``calculation_id`` equals the page id. ``scope`` entries are MathJS-serialised:
    ``[{"name": "span", "value": "10 m"}, {"name": "load", "value": "45 kN / m"}]``.

    NOTE: dataset variables (VLOOKUP) are NOT included in the simpleCalculate scope —
    they always report "Undefined symbol" even when the dataset works in the UI.
    """
    d = gql(
        """query SimpleCalculate($workspaceId: ID!, $calculationId: ID!, $scope: [ScopeNamedValueInput!]!) {
             simpleCalculate(workspaceId: $workspaceId, calculationId: $calculationId, scope: $scope) {
               calculationId
               statements {
                 statementId title formula engine
                 namedValues { name value }
                 errors warnings
               }
               scope {
                 name value type
                 artifacts {
                   ... on ImageArtifact { location bucket type signedUrl }
                 }
               }
             }
           }""",
        {"workspaceId": workspace_id, "calculationId": calculation_id,
         "scope": scope or []},
    )
    return d["simpleCalculate"]


# ---- CSV DATASET UPLOAD ----

def upload_csv_dataset(workspace_id: str, page_id: str, file_name: str,
                       csv_content: str) -> str | None:
    """Upload a CSV dataset to a page via the presigned S3 flow.

    After uploading, wait at least 60 seconds before inserting MDX that uses VLOOKUP
    against this dataset — the server must process the file first.

    The dataset name comes from the CSV filename (sans ``.csv``). **No leading
    underscore** in the filename — ``_chain_catalog.csv`` silently produces 0
    variables; ``chain_catalog.csv`` works.

    Returns the file id on success, or None if the presigned URL could not be obtained.
    """
    d = gql(
        """mutation($w: ID!, $p: ID!, $f: String!, $t: String!){
             createPresignedUploadPost(workspaceId: $w, pageId: $p, fileName: $f, fileType: $t){
               presignedPost { url fields } file { id }
             }
           }""",
        {"w": workspace_id, "p": page_id, "f": file_name, "t": "text/csv"},
    )
    pp = d.get("createPresignedUploadPost")
    if not pp:
        return None
    presigned = pp["presignedPost"]
    # Build multipart/form-data manually (stdlib only, no requests)
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in presigned["fields"].items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
            f"{v}\r\n".encode()
        )
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
        f"Content-Type: text/csv\r\n\r\n".encode()
        + csv_content.encode("utf-8")
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        presigned["url"], data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=GQL_TIMEOUT_S) as res:
            pass  # 200 or 204 is success
    except urllib.error.HTTPError as e:
        if e.code not in (200, 204):
            raise CalcTreeError(f"CSV upload failed: HTTP {e.code}") from None
    return pp["file"]["id"]


# ---- STATEMENT TITLES ----

TITLED_COMPONENTS = (
    "Assignment|EquationBlock|Python|SelectInput|RadioInput|SimpleInput|"
    "MatrixBlock|TrafficLights|InputTable"
)
_BLOCK_RE = re.compile(
    rf"<({TITLED_COMPONENTS})\b([\s\S]*?)(?:/>|>([\s\S]*?)</\1>)"
)
_NAME_RE = re.compile(r'\bname\s*=\s*"([^"]*)"')
_ATTR_FORMULA_RE = re.compile(r"""\bformula\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_FENCED_RE = re.compile(r"```[a-z]*\n([\s\S]*?)```")
_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=(?!=)")


def parse_mdx_blocks(mdx: str) -> list[dict]:
    """Pull `name` plus the variables each block assigns, in document order."""
    out = []
    for m in _BLOCK_RE.finditer(mdx):
        component, attrs, inner = m.group(1), m.group(2) or "", m.group(3) or ""
        name_m = _NAME_RE.search(attrs)
        if not name_m:
            continue
        name = name_m.group(1)
        attr_formula = _ATTR_FORMULA_RE.search(attrs)
        fenced = _FENCED_RE.search(inner)
        src = ""
        if attr_formula:
            src = attr_formula.group(1) or attr_formula.group(2) or ""
        elif fenced:
            src = fenced.group(1)
        src = (src.replace("&#10;", "\n").replace("&lt;", "<")
                  .replace("&gt;", ">").replace("&amp;", "&"))
        assigns = [m2.group(1) for m2 in
                   (_ASSIGN_RE.match(line) for line in src.split("\n")) if m2]
        # <InputTable name="_x"> carries no formula: it imports as `_x = cttable(...)`,
        # so the name IS the variable it defines. Without this it has no assigns, gets
        # filtered out, and stays "Untitled Statement".
        if component == "InputTable" and not assigns:
            assigns.append(name)
        out.append({"component": component, "name": name, "assigns": assigns})
    return out


# 30s: server-side evaluation of a page of formulas settles well inside this; past it
# the graph is not going to evaluate and waiting longer will not help.
# 3 attempts: each retry re-reads the statement ids, and in observed runs a single
# retry was always enough. The third exists only so one unlucky run is not fatal.
TITLE_SETTLE_TIMEOUT_S = 30.0
TITLE_ATTEMPTS = 3
# 1.5s between polls: fast enough that the common case adds no noticeable delay,
# slow enough not to hammer the endpoint through a 30s wait.
POLL_INTERVAL_S = 1.5


def apply_mdx_statement_titles(workspace_id: str, page_id: str, mdx: str,
                               settle_timeout_s: float = TITLE_SETTLE_TIMEOUT_S,
                               attempts: int = TITLE_ATTEMPTS) -> dict:
    """LEGACY: set statement titles from the `name` attributes in the MDX.

    As of 2026-08-24, insertMDXContent sets titles automatically and this function
    is no longer needed for new pages. It remains available for repairing pages
    created before the fix, where statements may still be titled "Untitled Statement".
    """
    blocks = [b for b in parse_mdx_blocks(mdx) if b["assigns"]]
    if not blocks:
        return {"titled": 0, "unmatched": [], "untitledLeft": 0, "verified": True, "attempts": 0}

    def evaluated(c) -> bool:
        return bool(c["statements"]) and any(
            nv.get("name") for st in c["statements"] for nv in (st.get("namedValues") or [])
        )

    def wait_evaluated(timeout_s: float) -> dict:
        deadline = time.monotonic() + timeout_s
        c = get_page_context(workspace_id, page_id)
        while time.monotonic() < deadline and not evaluated(c):
            time.sleep(POLL_INTERVAL_S)
            c = get_page_context(workspace_id, page_id)
        return c

    last = {"titled": 0, "unmatched": [b["name"] for b in blocks],
            "untitledLeft": 0, "verified": False, "attempts": 0}

    for attempt in range(1, attempts + 1):
        ctx = wait_evaluated(settle_timeout_s)

        used: set[str] = set()
        updates: list[dict] = []
        for st in ctx["statements"]:
            names = {nv["name"] for nv in (st.get("namedValues") or []) if nv.get("name")}
            best, best_score = None, 0
            for block in blocks:
                if block["name"] in used:
                    continue
                score = sum(1 for a in block["assigns"] if a in names)
                if score > 0 and score > best_score:
                    best, best_score = block, score
            if not best:
                continue
            used.add(best["name"])
            updates.append({
                "statementId": st["statementId"], "title": best["name"],
                "formula": st["formula"], "engine": st["engine"],
            })

        unmatched = [b["name"] for b in blocks if b["name"] not in used]
        if not updates:
            return {"titled": 0, "unmatched": unmatched,
                    "untitledLeft": len(ctx["statements"]), "verified": True,
                    "attempts": attempt}

        create_or_update_calculation(workspace_id, page_id, updates)

        # Confirm rather than trust: poll until the intended titles are visible.
        intended = {u["statementId"]: u["title"] for u in updates}
        deadline = time.monotonic() + settle_timeout_s
        pending = list(intended)
        while True:
            after = get_page_context(workspace_id, page_id)
            by_id = {st["statementId"]: st for st in after["statements"]}
            pending = [sid for sid, want in intended.items()
                       if (by_id.get(sid) or {}).get("title") != want]
            if not pending or time.monotonic() >= deadline:
                break
            time.sleep(POLL_INTERVAL_S)

        untitled_left = sum(
            1 for st in after["statements"]
            if not st.get("title") or st["title"] == "Untitled Statement"
        )
        last = {"titled": len(updates) - len(pending), "unmatched": unmatched,
                "untitledLeft": untitled_left, "verified": not pending,
                "attempts": attempt}
        if not pending:
            return last
        # Stale ids: fall through and re-read them.

    return last


# ---- the whole write path in one call ----

def build_page(workspace_id: str, title: str, mdx: str,
               parent_id: str | None = None) -> dict:
    """create page + register in tree -> insert MDX -> read back. Returns the page,
    the insert counts and the settled statements.

    insertMDXContent now sets statement titles from the MDX name attribute
    automatically (fixed on prod 2026-08-24), so a separate title pass is no
    longer needed.
    """
    page = create_page_in_tree(workspace_id, title, parent_id=parent_id)
    inserted = insert_mdx_content(workspace_id, page["id"], mdx)
    if inserted["statementsCreated"] == 0 and inserted["insertedCount"] > 0:
        raise CalcTreeError(
            f"insertMDXContent inserted {inserted['insertedCount']} node(s) but created 0 "
            "statements: the page will look correct and not compute"
        )
    if inserted.get("warnings"):
        raise CalcTreeError(
            "insertMDXContent skipped part of the content: " + "; ".join(inserted["warnings"])
        )
    time.sleep(2)  # settle before reading back
    ctx = get_page_context(workspace_id, page["id"])
    return {"page": page, "inserted": inserted,
            "statements": ctx["statements"], "url": page_url(workspace_id, page["id"])}


def audit_untitled(workspace_id: str, page_ids: list[str]) -> dict:
    """Find pages carrying statements still titled "Untitled Statement".

    LEGACY: useful for pages created before 2026-08-24, when insertMDXContent did
    not set titles. New pages should not need this.
    """
    findings = []
    for pid in page_ids:
        ctx = get_page_context(workspace_id, pid)
        untitled = [st for st in ctx["statements"]
                    if not st.get("title") or st["title"] == "Untitled Statement"]
        if untitled:
            findings.append({
                "pageId": pid,
                "title": (ctx.get("page") or {}).get("title"),
                "untitled": len(untitled),
                "total": len(ctx["statements"]),
                "url": page_url(workspace_id, pid),
            })
    return {"checked": len(page_ids), "affected": findings}


# ---- CLI ----

def _fmt_value(raw) -> str:
    v = raw
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except (ValueError, TypeError):
            return str(raw)
    if isinstance(v, dict) and v.get("mathjs") == "Unit":
        return f"{_js_number(v.get('value'))} {v.get('unit')}"
    return json.dumps(v, separators=(",", ":"))


def _print_statements(statements: list[dict]) -> None:
    for s in statements:
        print(f"  [{s['engine']}] {s.get('title')!r}")
        for nv in s.get("namedValues") or []:
            if nv.get("name"):
                print(f"      {nv['name']} = {_fmt_value(nv.get('value'))}")
        if s.get("errors"):
            print(f"      ERRORS: {s['errors']}")


USAGE = """usage: python3 calctree_api.py <command> [args]

  pages       <workspaceId>
  context     <workspaceId> <pageId>
  execute     <workspaceId> <pageId> [name=value ...]   run a page with custom inputs
  create      <workspaceId> <title> [parentId]
  insert      <workspaceId> <pageId> <file.mdx|->
  titles      <workspaceId> <pageId> <file.mdx|->
  build       <workspaceId> <title> <file.mdx|->     create + insert + read back
  upload-csv  <workspaceId> <pageId> <file.csv>      upload a CSV dataset
  reference   <workspaceId> <targetPageId> <sourcePageId> [alias]
  audit       <workspaceId> <pageId>... | -   report statements left "Untitled Statement"
  templates   <workspaceId> [keyword ...]            list templates (own + built-in)
  page-templates <workspaceId> <pageId>             templates saved from a page
  pdf         <workspaceId> <pageId> [title] [fileName]  generate PDF report
  delete      <workspaceId> <pageId>                 soft delete

'-' reads the MDX from stdin. Requires CALCTREE_API_KEY."""


def _read_mdx(path: str) -> str:
    return sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd, args = argv[1], argv[2:]
    try:
        if cmd == "pages":
            for p in list_workspace_pages(args[0]):
                print(f"  {p['id']}  {p['title']!r}")
        elif cmd == "context":
            ctx = get_page_context(args[0], args[1])
            print(f"page: {(ctx.get('page') or {}).get('title')!r}")
            print(f"{len(ctx['statements'])} statement(s)")
            _print_statements(ctx["statements"])
        elif cmd == "execute":
            scope = []
            for pair in args[2:]:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    scope.append({"name": k, "value": v})
            r = simple_calculate(args[0], args[1], scope)
            print(f"calculationId: {r['calculationId']}")
            print(f"{len(r['statements'])} statement(s)")
            _print_statements(r["statements"])
        elif cmd == "create":
            page = create_page_in_tree(args[0], args[1], args[2] if len(args) > 2 else None)
            print(f"{page['id']}\n{page_url(args[0], page['id'])}")
        elif cmd == "insert":
            r = insert_mdx_content(args[0], args[1], _read_mdx(args[2]))
            print(f"insertedCount={r['insertedCount']} statementsCreated={r['statementsCreated']}")
            for w in r.get("warnings") or []:
                print(f"WARNING: {w}", file=sys.stderr)
            if r.get("warnings"):
                return 1
            if r["statementsCreated"] == 0 and r["insertedCount"] > 0:
                print("WARNING: nodes inserted but no statements created", file=sys.stderr)
                return 1
        elif cmd == "titles":
            r = apply_mdx_statement_titles(args[0], args[1], _read_mdx(args[2]))
            print(f"titled={r['titled']} unmatched={r['unmatched']} "
                  f"untitledLeft={r['untitledLeft']} verified={r['verified']} attempts={r['attempts']}")
            if not r["verified"]:
                return 1
        elif cmd == "build":
            r = build_page(args[0], args[1], _read_mdx(args[2]))
            print(f"page {r['page']['id']}")
            print(f"  insertMDXContent: {r['inserted']['insertedCount']} nodes, "
                  f"{r['inserted']['statementsCreated']} statements")
            _print_statements(r["statements"])
            print(r["url"])
        elif cmd == "upload-csv":
            csv_data = open(args[2], encoding="utf-8").read()
            fid = upload_csv_dataset(args[0], args[1], os.path.basename(args[2]), csv_data)
            if fid:
                print(f"uploaded: fileId={fid}")
                print("wait at least 60s before inserting MDX that uses VLOOKUP against this dataset")
            else:
                print("upload failed: no presigned URL returned", file=sys.stderr)
                return 1
        elif cmd == "reference":
            r = reference_page_via_api(args[0], args[1], args[2],
                                       args[3] if len(args) > 3 else None)
            print(f"alias={r['alias']} values={r['count']} statementId={r['statementId']}")
        elif cmd == "audit":
            ids = ([l.strip() for l in sys.stdin if l.strip()]
                   if args[1:] == ["-"] else args[1:])
            if not ids:
                print("audit needs page ids (or '-' to read them from stdin)", file=sys.stderr)
                return 2
            r = audit_untitled(args[0], ids)
            print(f"checked {r['checked']} page(s); {len(r['affected'])} carry untitled statements")
            for f in r["affected"]:
                print(f"  {f['untitled']}/{f['total']} untitled  {f['title']!r}\n    {f['url']}")
            return 1 if r["affected"] else 0
        elif cmd == "templates":
            for t in list_templates(args[0], args[1:]):
                kind = "builtin" if not t.get("workspace") else "workspace"
                pub = "published" if t.get("latestVersionId") else "NEVER PUBLISHED"
                print(f"  {t['id']}  {t['name']!r}  [{kind}, {pub}]")
        elif cmd == "page-templates":
            for t in page_templates(args[0], args[1]):
                v = t.get("latestVersion")
                print(f"  {t['templateId']}  {t['name']!r}  "
                      f"latestVersion={v if v is not None else 'NEVER PUBLISHED'}")
        elif cmd == "pdf":
            title = args[2] if len(args) > 2 else "Report"
            fname = args[3] if len(args) > 3 else "report"
            print(f"creating PDF for page {args[1]}...")
            r = create_pdf_report(args[0], [args[1]], title, fname)
            print(f"ready ({r['fileSize']} bytes)")
            print(r["signedUrl"])
        elif cmd == "delete":
            delete_page(args[0], args[1])
            print("deleted (soft)")
        else:
            print(USAGE)
            return 2
    except IndexError:
        print(USAGE)
        return 2
    except CalcTreeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
