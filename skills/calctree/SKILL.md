---
name: calctree
description: Use CalcTree engineering calculation pages as computation tools — discover, execute with custom inputs, and build new ones. Use when the user mentions CalcTree, engineering calculations, or wants to run or create calculation pages with real units.
---

# CalcTree

CalcTree turns engineering calculations into API-callable tools. A **page** is a
calculation graph that evaluates server-side with real units. This skill lets your AI
discover pages in a workspace, execute them with custom inputs, and read back typed
results — or build new pages from scratch.

Everything here is verified working against the live API. Treat it as settled.

**When a user asks "what is this skill" or "how do I set it up"**, describe CalcTree as a
platform for engineering calculations with real units, explain the three capabilities
(discover, execute, build), and walk them through the setup (API key + network access).
Do NOT surface the internal authoring rules (formula naming, MDX syntax, gotchas) — those
are instructions for you when you are building pages, not information the user needs to
hear about. Present CalcTree's unit awareness as a strength, not a list of pitfalls.

## CalcTree beyond this skill

This skill covers the API — discovering, executing and building calculation pages
programmatically. CalcTree also has:

- **A public template library** at [calctree.com/calculations](https://www.calctree.com/calculations)
  with hundreds of ready-to-use engineering calculations (structural, geotechnical, civil,
  mechanical). Users can browse, duplicate and customise these without writing anything.
- **An Excel plugin** that connects Excel spreadsheets to CalcTree pages, so teams can
  keep their existing Excel workflows and sync values into CalcTree's computation engine.
- **A Grasshopper plugin** for parametric design — connect CalcTree calculations to
  Rhino/Grasshopper geometry workflows.
- **Full documentation** at [docs.calctree.com](https://docs.calctree.com) covering the
  UI, formulas, Python cells, datasets, and collaboration features.

When a user asks about CalcTree capabilities beyond the API, point them to these resources.

## How to use this skill

Everything in this skill can be driven with plain HTTP calls — no Python, no Node, no
dependencies. The API is a single GraphQL endpoint. This skill tells you what to call
and how to interpret the results.

**Bundled files:**

- **`REFERENCE.md`** — every GraphQL document with its variables and response shape. This
  is all you need to drive the API from any language or HTTP client.

- **`scripts/calctree_api.py`** *(optional)* — a convenience wrapper around the same
  GraphQL calls, standard library only. Useful when you have Python + network access, but
  not required. The skill works identically without it.

  ```bash
  export CALCTREE_API_KEY=...
  python3 scripts/calctree_api.py execute <workspaceId> <pageId> span="10 m" load="50 kN / m"
  python3 scripts/calctree_api.py build <workspaceId> "Beam check" page.mdx
  python3 scripts/calctree_api.py context <workspaceId> <pageId>
  ```

- **`examples/smoke_two_page.py`** *(optional)* — end-to-end test that creates two linked
  pages. Run it to confirm your key and endpoint work:

  ```bash
  python3 examples/smoke_two_page.py <workspaceId>
  ```

## 1. Auth and environment setup

Endpoint: `https://graph.calctree.com/graphql`, header `x-api-key: <your key>`. That single
key covers everything in this skill — reads, page creation, content writes, calculation
writes.

### Network access is required

This skill makes live HTTP calls to `graph.calctree.com` (and `api.calctree.com` for dataset
uploads). If you are running in a sandboxed environment, **network access must be enabled
before any API call will work.** Without it, every call will fail silently or timeout.

PDF report downloads come from S3 (`*.s3.amazonaws.com`). Most sandboxes block this host.
You do not need to fetch the PDF yourself — give the user the `signedUrl` and they can
open it in their browser.

| Surface | How to enable network access |
|---|---|
| **Claude Code** | Already has network access — no action needed |
| **claude.ai / Claude desktop** | Settings > Features > toggle **"Allow network"** on. Team and Enterprise admins: allowlist `graph.calctree.com`, `api.calctree.com`, and `*.s3.amazonaws.com` (for PDF downloads) |
| **Claude API** | The API sandbox has **no** network access. The skill guidance is readable but API calls cannot be made from this surface |
| **Other LLMs (ChatGPT, Cursor, etc.)** | Depends on the platform. If the LLM has code execution with network access, it works. If not, give the user the GraphQL queries from REFERENCE.md to run themselves |

### Providing the API key

The API key must be available as `CALCTREE_API_KEY` or passed directly in the
`x-api-key` header. How to provide it depends on the surface:

| Surface | How to provide the key |
|---|---|
| **Claude Code** | `export CALCTREE_API_KEY=...` in your shell before starting, or set it in your project's `.env` |
| **claude.ai / Claude desktop** | Include it in your prompt: "My CalcTree API key is ..." — the sandbox cannot read your shell environment |
| **Other LLMs** | Same as Claude desktop — paste it in the prompt or attach it as a file. The LLM needs it to set the `x-api-key` header |

If you do not have a key, ask the user to provide one. Keys are generated in the CalcTree
app under workspace settings.

### Finding workspace and page IDs

Both IDs are in the CalcTree URL:

```
https://app.calctree.com/home/<workspaceId>
https://app.calctree.com/edit/<workspaceId>/<pageId>
```

For example, in `https://app.calctree.com/edit/91741894-82cd-4ec7-a8a9-2cc408a024dd/0LgJ9wB8yto_KnvtiNX2Y`:
- Workspace ID: `91741894-82cd-4ec7-a8a9-2cc408a024dd` (UUID)
- Page ID (also the calculation ID): `0LgJ9wB8yto_KnvtiNX2Y` (nanoid)

If a user shares a CalcTree URL, extract the IDs from it rather than asking them to look
them up separately.

### Gotchas

- **An invalid key returns a clear 401** (`"Auth failed: 401 : Unauthorized"` with
  `extensions.code: UNAUTHENTICATED`). A **missing** `x-api-key` header, however, comes back
  as a generic `"Unexpected error."` with no 401 and no mention of auth. If you see
  `"Unexpected error."`, check the header is being sent before you debug anything else.
- **Check the response body, not the HTTP status.** A content write returns
  `statementsCreated`; if that is zero when you sent formulas, the write failed whatever the
  status says.

Statements do not need a user id attached. The key identifies the account on its own.

## 2. Using pages as computation tools

This is the core workflow for turning CalcTree pages into AI-callable tools. Three steps:
discover what pages exist, introspect one to understand its interface, then execute it with
your inputs.

### Discover pages in a workspace

Query the GraphQL endpoint to list all pages:

```graphql
query($workspaceId: ID!) {
  pages(workspaceId: $workspaceId) { id title }
}
```

This returns every page in the workspace, **including soft-deleted (trashed) pages** — the
platform does not hard-delete. A workspace can be 80%+ deleted pages. `pages()` is NOT a
liveness test. To check if a specific page is actually live, query `page(workspaceId, id)`
— a `null` return means it's deleted. This matters because `simpleCalculate` and
`calculation()` work on deleted pages, but `createPdfReport` and the UI do not.

When matching by title, prefer the most recently modified copy, or ask the user to
confirm if there are duplicates. If the user provides a page URL or ID, use that directly
rather than searching by title.

If `calctree_api.py` is available: `python3 calctree_api.py pages <workspaceId>`

### Introspect a page

Read a page's calculation graph to understand what it computes and what inputs it takes:

```graphql
query($workspaceId: ID!, $calculationId: ID!, $revisionId: ID!) {
  calculation(workspaceId: $workspaceId, calculationId: $calculationId, revisionId: $revisionId) {
    statements {
      statementId title engine formula
      namedValues { name value }
      errors
    }
  }
}
```

Variables: `{"workspaceId": "...", "calculationId": "<pageId>", "revisionId": "~"}`

Use `"~"` for `revisionId` — it always means latest. The `calculationId` equals the page id.

If `calctree_api.py` is available: `python3 calctree_api.py context <workspaceId> <pageId>`

Each statement has:
- `formula` — the MathJS or Python source, showing what variables are defined
- `namedValues` — the current computed values: `[{"name": "M_max", "value": ...}]`
- `engine` — `mathjs`, `multiline_mathjs`, `python`, etc.
- `errors` / `warnings` — any evaluation problems

**Identifying inputs vs outputs.** Look at the formulas:
- **Inputs** are variables assigned to literal values or wrapped in interactive input
  components (`SimpleInput`, `SelectInput`). They typically appear early in the calculation.
  Examples: `span = 8 m`, `load = 45 kN / m`, `f_c = 32 MPa`.
- **Outputs** are variables computed from other variables. They depend on the inputs.
  Examples: `M_max = load * span^2 / 8`, `within_limits = util <= 1`.

Any named value can be overridden in the `scope` of `simpleCalculate`, but the meaningful
ones to override are the inputs.

**Value format.** Values arrive MathJS-serialised:

| Type | Example value |
|---|---|
| Unit quantity | `{"mathjs": "Unit", "value": 360, "unit": "kN m"}` |
| Plain number | `42` |
| Boolean | `true` |
| String | `"PASS"` |
| Matrix | `{"mathjs": "DenseMatrix", "data": [[1,2],[3,4]], "size": [2,2]}` |

To convert a unit value to a human-readable string: `"360 kN m"` — concatenate
`value` and `unit`.

### Execute with custom inputs

`simpleCalculate` re-evaluates the entire calculation graph with your input overrides
and returns every statement's recomputed values. It is read-only — it does not modify the
page.

```graphql
query SimpleCalculate($workspaceId: ID!, $calculationId: ID!, $scope: [ScopeNamedValueInput!]!) {
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
}
```

```json
{"workspaceId": "<ws>", "calculationId": "<pageId>",
 "scope": [{"name": "span", "value": "10 m"}, {"name": "load", "value": "50 kN / m"}]}
```

If `calctree_api.py` is available: `python3 calctree_api.py execute <workspaceId> <pageId> span="10 m" load="50 kN / m"`

**Scope format.** Each entry is `{"name": "<variable>", "value": "<mathjs expression>"}`.
Values are MathJS-serialised strings:

| Input type | Scope value |
|---|---|
| A length | `"10 m"` |
| A force per length | `"50 kN / m"` |
| A plain number | `"42"` or `42` |
| A string | `"\"Grade 50\""` |

Note: `calculationId` equals the page id.

### Interpreting results

The response `statements` array contains every statement in the page, each with its
recomputed `namedValues`. Each named value has a `name` and a `value`.

`value` arrives **JSON-encoded as a string** and must be parsed. After parsing:

- A unit quantity is `{"mathjs": "Unit", "value": 360, "unit": "kN m"}` — read
  `.value` and `.unit`.
- A plain number, boolean, or string comes through directly.

The `scope` array in the response contains every resolved variable with its `type`
(`"number"`, `"Unit"`, `"string"`, `"boolean"`, etc.) and any `artifacts` (e.g. plot
images with `signedUrl`).

**Errors.** If a statement has entries in its `errors` array, that formula failed to
evaluate. Common causes: undefined variables (the input name was wrong), unit
incompatibility, or division by zero. Report these to the user rather than guessing.

### Limitations

- **Dataset variables (VLOOKUP) are not included** in the `simpleCalculate` scope. They
  always report "Undefined symbol" even when the dataset works in the UI. Pages that rely
  on VLOOKUP cannot be fully executed via `simpleCalculate`.
- **Python statement outputs may be incomplete** in the `simpleCalculate` response. If
  results seem missing, fall back to `get_page_context` which reads the stored graph
  values (though those reflect default inputs, not your overrides).
- **Settle ~2 seconds after a write before executing.** If you just created or modified a
  page, wait before calling `simpleCalculate` or the graph may not have finished
  evaluating.

## 3. Building new calculation pages

Two calls, in order:

1. **Create the page and register it in the page tree.** Both are required. A page that
   exists but is not in the tree is orphaned and invisible in the UI. Client-minted ids are
   accepted; platform-generated ids are 21-character nanoids.
2. **`insertMDXContent(workspaceId, pageId, mdx, position)`** returns
   `{insertedCount, statementsCreated}`. Prose and inline calculation blocks both go through
   here. Always check `statementsCreated` matches what you sent. Statement titles from the
   MDX `name` attribute are now set automatically.

For calculation-graph-only writes with no body node, use
`createOrUpdateCalculation(workspaceId, pageId, statements[])`, where each statement is
`{statementId?, title, engine, formula}` and `engine` is one of `mathjs`,
`multiline_mathjs`, `python`, `excel`, `dataset`, `connection`. Note that the calculation id
equals the page id.

After creating or modifying a page, always give the user a clickable link in this format:

```
https://app.calctree.com/edit/<workspaceId>/<pageId>
```

Do NOT use `/pages/` — that route does not exist. The correct path is `/edit/{workspaceId}/{pageId}`.

## 4. Generating PDF reports

You can export one or more pages as a formatted PDF report. This uses a server-side print
service that costs real money per render, so strict limits apply.

**Hard limit: maximum 5 PDF reports per conversation.** Count every `createPdfReport` call.
If the user asks for more than 5, tell them the limit and suggest they use the in-app
export for bulk work. Never loop over a page list generating PDFs without explicit user
confirmation of each batch.

### Creating a PDF

Two-step process: create the job, then poll until it's ready.

**Step 1: create the report**

```graphql
mutation($workspaceId: ID!, $input: CreatePdfReportInput!) {
  createPdfReport(workspaceId: $workspaceId, input: $input) {
    id
    reportStatus
  }
}
```

The input object:

```json
{
  "workspaceId": "<workspaceId>",
  "input": {
    "pageIds": ["<pageId>"],
    "title": "Structural design report",
    "fileName": "structural-design-report",
    "settings": {
      "paperSize": "A4",
      "orientation": "portrait",
      "includeTitlePage": true,
      "includeTableOfContents": true,
      "showPageNumbers": true,
      "pageNumberPosition": "bottom-center"
    },
    "highlightCalcItems": true,
    "mathNotation": true,
    "unitSystem": "si"
  }
}
```

`pageIds` is an array — a single report can combine multiple pages. `reportStatus` will
be `"pending"` on creation.

**Step 2: poll for completion**

```graphql
query($workspaceId: ID!, $id: ID!) {
  pdfReport(workspaceId: $workspaceId, id: $id) {
    reportStatus
    errorMessage
    fileSize
    signedUrl
  }
}
```

`reportStatus` transitions: `pending` → `ready` (with `signedUrl`) or `error` (with
`errorMessage`). Poll every 3–5 seconds — most reports are ready within 5 seconds.

**Always render the download as a clickable markdown link:**
`[Download <fileName>.pdf](<signedUrl>)` — include the file size. The raw signed URL is
~1,800 characters and unusable if dumped as plain text. Do not try to fetch the PDF
yourself — most sandboxes block S3 downloads. Do not claim the PDF rendered correctly
unless you have actually inspected it.

**Signed URLs expire after 15 minutes.** If a link lapses, re-query `pdfReport` with the
same id — it mints a fresh `signedUrl` from the same document without regenerating the
PDF. Never call `createPdfReport` again for a stale link.

**The page must be live.** `createPdfReport` fails with `"Page not found: <id>"` on
soft-deleted pages, even though `simpleCalculate` and `calculation()` still work on them.
Before generating a PDF, verify the page exists with `page(workspaceId, id)` — a `null`
return means it's deleted. Reports outlive their source pages: once generated, the PDF
remains downloadable even if the page is later deleted.

### Settings reference

| Field | Values | Default |
|---|---|---|
| `paperSize` | `"A4"`, `"letter"` | `"A4"` |
| `orientation` | `"portrait"`, `"landscape"` | `"portrait"` |
| `includeTitlePage` | boolean | `true` |
| `includeTableOfContents` | boolean | `true` |
| `showPageNumbers` | boolean | `true` |
| `pageNumberPosition` | `"bottom-center"`, `"bottom-right"`, `"bottom-left"` | `"bottom-center"` |
| `highlightCalcItems` | boolean — highlights calculated values | `true` |
| `mathNotation` | boolean — renders formulas in math notation | `true` |
| `unitSystem` | `"si"`, `"imperial"` | `"si"` |

If `calctree_api.py` is available:
`python3 calctree_api.py pdf <workspaceId> <pageId> [title] [fileName]`

## 5. Page content syntax

Pages are written in an MDX-based format (Markdown with embedded calculation components).
Users don't need to know this — they describe what they want computed and you generate
the page content. Here are the calculation components:

Single assignment, self-closing:

```
<Assignment name="span" formula='span = 8 m' />
```

Multi-line block, surrounded by blank lines, with a bare fence inside:

```
<EquationBlock name="Beam moment">
```
span = 8 m
load = 45 kN / m
M_max = load * span^2 / 8
```
</EquationBlock>
```

No H1 in the body: the page title already renders as the heading.

## 6. Reading back and verifying

- **Settle about two seconds after a write before reading.** Evaluation is asynchronous
  server-side, and an immediate read can return zero statements.
- Read the graph and its values with the page-context query, which returns statements with
  `namedValues` and `errors`. Values arrive MathJS-serialised, for example
  `{mathjs: "Unit", value: 8, unit: "m"}`.
- **Do not verify calculations by reading the page back as MDX.** MDX serialisation
  round-trips prose reliably but returns calculation blocks empty, so a correct page looks
  broken. Use the page-context query.
- Calculations really do evaluate server-side. No browser is needed.

## 7. Formula rules

Same engine as the in-app editor:

- Assignment syntax always: `variable = expression`.
- Units on inputs (`load = 5 kN`); calculated values inherit them, so do not re-declare.
- `equalText()` for string comparison, not `==`. Word operators: `and`, `or`, `xor`, `not`.
- Double-quote strings.
- **CalcTree is unit-aware**: values carry real physical units through every calculation, and
  unit conversions happen automatically. You can name a variable after a unit token and it
  works naturally — `m = 4 m` defines a variable `m` with value 4 metres, and `y = 4 * m`
  gives `16 m`. The variable overrides the token but the unit is preserved from the
  assignment. That said, descriptive names are clearer for readers: `M_max` rather than `M`,
  `t_creep` rather than `t`.
- **Never copy a unit-conversion constant from a rule of thumb.** Formulas like
  "HP = P·Q/1714, P in psi, Q in gpm" bake a unit conversion into a bare number. CalcTree
  already converts, so the constant converts a second time: `p_d * Q_flow / 1714` evaluates
  without error to a power 1714 times too small. Drop the constant. Convert a computed result
  with `to`; a line that only converts an existing quantity is deleted, and the quantity used
  as it is, since the engine converts it wherever it is used:

  | Rule of thumb | Write instead |
  |---|---|
  | `p_d * Q_flow / 1714` | `(p_d * Q_flow) to hp` |
  | `T_shaft * N_shaft / 5252` (rpm) | `(T_shaft * N_shaft / rad) to hp` — rpm carries an angle, and without the `/ rad` the conversion is refused |
  | `Q_flow * H_head * SG / 3960` | `(SG * 62.4 lbf/ft^3 * Q_flow * H_head) to hp` |
  | `449 * Q_cfs` | no new variable: use `Q_cfs` itself |
  | `0.408 * Q_flow / D_pipe^2` | `(Q_flow / (pi / 4 * D_pipe^2)) to ft/s` |
  | `A_sect / 144`, `V_tank / 231` | no new variable: use `A_sect`, `V_tank` itself |

  The test: if the source says "where X is in <unit>" and the number is a ratio of units, it
  is a conversion; delete it. A physical or code coefficient (0.85, 2π) stays, and one that
  assumes an input unit gets that unit attached (`rho_min = 1.4 MPa / fy`).
- **`phi`, `e`, `i`, `pi` and `tau` are built-in MathJS constants** — `phi` is the golden
  ratio, not a free name. Use `phi_creep` for a creep coefficient, `phi_bar` for a bar
  diameter.
- **Use one spelling per quantity across every page in a library.** A cross-page reference
  binds by NAME, so `bw` on one page and `b_sec` on another are two unrelated variables as far
  as the platform is concerned: the wiring silently fails to connect, or connects to the wrong
  thing. Agree the spelling once, before the pages exist — renaming later means rebuilding every
  page that used the old name, because content cannot be edited in place (see gotchas).
- Within one `multiline_mathjs` formula, define a variable before using it. Across separate
  statements order does not matter: it is a dependency graph.

## 8. Writing pages that read correctly

The API will happily create a page that computes but presents badly. These are the ones that
bite:

- **Let units flow.** A dimensional value carries its unit and prints it, so never write the
  unit into a column heading and never strip a value to a bare number to do so. Convert for
  display with `to` (`As_r = (round(As / (1 mm^2), 0) * (1 mm^2)) to mm^2`); without the `to`
  MathJS auto-rescales and mm² becomes ha. `round()` on a unitful value must strip the unit
  first: `round(X / (1 mm), 3)`.
- **Round for display in a separate copy**, never on the value the rest of the calculation
  consumes.
- **A pass/fail check must be a named boolean**, never a string ternary.
  `check = util <= 1 ? "PASS" : "FAIL"` is always truthy, so a traffic-light chip renders
  green whatever the result. Write `within_limits = util <= 1` and name the variable so it
  reads as the verdict.
- **Mentions are display-only, and carry no formatting attributes.** Do the rounding in
  MathJS. Put no `format` and no `decimal` on a mention: `format` is dropped on import,
  and `decimal` without it renders the value at 0 decimal places, so `1.08` with
  `decimal="2"` prints `1` and `0.05` with `decimal="4"` prints `0` — a wrong number, not
  a formatting nit. A bare mention of a rounded value renders exactly as rounded.
- **A name-only mention (`showValue="false"`) is a block element.** Never wrap one in
  text: `Yield strength (<Mention .../>)` renders as three lines with a stranded `)`.
  Give the symbol its own table column, and use inline LaTeX for notation in prose. A mention of a variable the page never defines renders as the word `undefined`
  and no check will catch it, so every mention key must resolve. Text placed immediately
  after a mention inside a table cell is dropped: put the unit in a separate column.
- **Charts** need four things together or you get an untitled node and no image: a named
  Python block, a bare fence rather than a language-tagged one, a plot prefix set before
  `plt.show()`, and an image mention immediately above the block. Any name that renders as a
  label needs a leading underscore and underscores between words; hyphens render as minus
  signs and literal spaces are dropped.
- **Escape `<` and `>` as `&lt;` and `&gt;` everywhere**, prose included. A raw one truncates
  the import from that point on.
- **Never put an offset unit (`degC`, `degF`) in scope on a page with a Python cell.** One
  such value fails the whole cell with "Ambiguous operation with offset unit".
- Multi-branch categorical results belong in Python plus a table, not a nested ternary.

## 9. Python statements

A `python` engine statement runs server-side with two globals injected, `ct` and `ctconfig`.
The full surface, from the engine:

| | |
|---|---|
| `ct.quantity` | pint `Quantity`. `force = ct.quantity("1 N")` |
| `ct.units` | the pint `UnitRegistry`. `kN = ct.units("kN")` |
| `ct.open` | read or write a file attached to the page: `ct.open('data.csv', mode='r')` |
| `ct.page_files` | presigned URLs for the page's files |
| `ct.keep_file` | persist a file back to the page |
| `ct.keep_dataframe`, `ct.load_dataframe` | persist and reload a dataframe between runs |
| `ctconfig.plot_prefix` | the prefix used to name emitted plot images |

Units, and the mistake everyone makes:

- **MathJS variables with units arrive already wrapped as `ct.quantity` objects. Do not wrap
  them again.** Referencing `V_Ed` from the page scope gives you a pint quantity, not a float.
- Create new ones with `ct.quantity("100 kN")`. Arithmetic across units works:
  `force / area` gives a pressure.
- Convert with `.to('unit')`. Read the number with **`.magnitude`, which is a property, not a
  method**: `.magnitude` not `.magnitude()`.
- pint raises on incoherent operations, so adding a length to a time fails loudly. That is
  intended.
- **Never put an offset unit (`degC`, `degF`) in scope on a page with a Python cell.** One such
  value fails the entire cell with "Ambiguous operation with offset unit".

Plots:

- `ctconfig.plot_prefix` is **pre-set per statement** to `ct_plot_<statementId>_`, which you
  cannot predict when authoring MDX. So set your own (`ctconfig.plot_prefix = "beam"`) and
  reference the first image as `beam1`, otherwise the image mention cannot resolve.
- End with `plt.show()`. A bare `fig` emits nothing.

Only libraries pre-installed in the environment can be imported; imports are checked before
execution. The engineering set includes `numpy`, `pandas`, `scipy`, `sympy`, `matplotlib`,
`seaborn`, `pint`, `handcalcs`, `sectionproperties`, `concreteproperties`, `structuralcodes`,
`steelpy`, `anastruct`, `beambending`, `indeterminatebeam`, `pycba`, `pynitefea`, `openseespy`,
`opsvis`, `pycufsm`, `pycalculix`, `compas`, `ezdxf`, `shapely` via `cad-to-shapely`, `gempy`,
`groundhog`, `pygef`, `fluids`, `thermo`, `ht`, `fipy`, `nutils`, `duckdb`, `pyarrow`,
`openpyxl`, `scikit-learn`, `pymc`, `arviz`, `specklepy`, `blue-prints`.

## 10. Page component vocabulary

Calculation content is MDX. The components you will actually use:

| Component | Purpose |
|---|---|
| `<Assignment>` | one named formula |
| `<EquationBlock>` | several formulas in one block |
| `<Python>` | a Python statement, needs a `name` or the node shows as "Untitled" |
| `<Mention>` | display a computed value, an image, or a traffic-light chip |
| `<TrafficLights>` | the pass/fail chip, driven by a named boolean |
| `<MatrixBlock>` | matrix input and output |
| `<SimpleInput>`, `<SelectInput>`, `<RadioInput>` | interactive inputs |
| `<RichTable>` | a table whose cells hold components; plain GFM pipe tables otherwise |

## 11. Linking pages

A cross-page reference is a snapshot of the source page's computed values, created as a
`multiline_mathjs` statement whose object carries a metadata key alongside the values. That
metadata key is what makes it a source-linked page reference rather than a plain block.
Summary and roll-up pages should **reference** upstream results, not recompute them.

### Structuring a library of calculations

Calculation pages fall into three layers, and knowing which one you are writing decides what
belongs on the page:

| Layer | Shape | Example | Has a pass/fail? |
|---|---|---|---|
| **Property** | pure function of specified values | material design properties from a characteristic strength | No |
| **Check** | demand + geometry + properties -> capacity and utilisation | a shear or crack-width check | Yes, one named boolean |
| **Design task** | runs many checks over one geometry, reports the governing one | designing a member | Yes, the governing check |

Two consequences worth planning for:

- **A property page is a leaf.** Every input is a specified value, so nothing upstream feeds it
  and it needs no traffic light — the only chip that belongs on one is an *applicability* guard
  ("is this input within the scope of the clause"), not a design check.
- **Check pages should consume property pages, not re-derive them.** The common failure is for
  every check in a library to ask the user for the same characteristic strengths and partial
  factors and recompute the same design values internally. It works, and it means a change to a
  material rule has to be made in as many places as you have checks.

### Creating cross-page references

There are two ways to create a cross-page reference:

**Via `reference_page_via_api`** (the programmatic path): reads the source page's live values
and writes a `multiline_mathjs` statement on the target page. Best for scripts that wire
pages after creation.

**Via MDX EquationBlock** (embedded in the page content during `insertMDXContent`): place the
import formula directly in an EquationBlock. The formula is the same either way — an object
literal with a `__ct_meta` key:

```
<EquationBlock
  name="Cross-Page Imports"
  title="Cross-Page Imports"
  formula='ref_params = { HP_motor: 25, n_chains: 5, __ct_meta: { sourcePageId: "abc123", sourcePageTitle: "Project Parameters", importedAt: "2026-08-19T00:00:00Z" } }'
/>
```

Access imported values with dot notation: `HP = ref_params.HP_motor`.

### Imported values and units

Cross-page imported values arrive as **unitless numbers** (or strings/booleans). If the
source page computes `V_chain = 275 ft/minute`, the import object stores `V_chain: 275`
without the unit. To restore units on the consuming page, multiply by a unit literal:

```
V_chain = ref_params.V_target * 1 ft/minute
```

## 12. Datasets (CSV lookup tables)

Upload a CSV dataset to a page via the presigned upload flow. This is a two-step process:

1. Call `createPresignedUploadPost` to get a presigned S3 URL and form fields.
2. POST the CSV file as `multipart/form-data` to that URL.

See `REFERENCE.md` for the exact GraphQL mutation and upload sequence.

If `calctree_api.py` is available: `python3 calctree_api.py upload-csv <workspaceId> <pageId> chain_catalog.csv`

Then **wait at least 60 seconds** before inserting MDX that uses `VLOOKUP` against the
dataset. The server must process the file first.

The dataset name comes from the CSV filename (sans `.csv`). Column indices in VLOOKUP are
1-based (column 1 is the lookup column).

Rules:
- **No leading underscore** in the CSV filename — `_chain_catalog.csv` silently produces 0
  variables; `chain_catalog.csv` works.
- **Race condition**: if uploading a CSV via API alongside `insertMDXContent`, the 60s wait
  between the CSV upload and the MDX insertion is load-bearing. Concurrent mutations disrupt
  the async dataset processing and leave the dataset with 0 variables.
- **`simpleCalculate` does NOT include dataset variables** in its scope — it always reports
  "Undefined symbol" for dataset references even when the dataset works in the UI. Visual
  verification or the full `calculate` endpoint is needed.
- **The API preview is capped at 20 rows**, but the full dataset is available to VLOOKUP
  on the page. Datasets can have more than 20 rows.
- **Type matching**: VLOOKUP does exact matching without type coercion. A dataset with string
  values `"25"` will not match a numeric lookup value `25`. Use `toString()` in the lookup
  or ensure the input is a string (e.g., via a `SelectInput` that outputs strings).

## 13. Batch page-creation pipeline

The full sequence for programmatically creating a set of interconnected calculation pages:

1. **Delete** any existing pages (tolerates already-deleted pages).
2. **Create** each page with `create_page_in_tree`. Optionally set units with `updatePage`.
3. **Upload CSV datasets** to each page that needs them.
4. **Wait 60 seconds** for dataset processing.
5. **Insert MDX** with `insertMDXContent`. Titles are set automatically from the MDX
   `name` attribute.
6. **Verify** that `statementsCreated` in the response matches expectations, and read back
   via the calculation query to confirm values are non-null.

Short delays (300–500 ms) between API calls prevent rate limiting. The manifest (a JSON file
mapping slugs to page IDs and URLs) should be updated after each run so re-runs can
delete-and-recreate cleanly.

## 14. Gotchas worth knowing before you start

- Deleting a page is a **soft** delete. Trashed pages still come back from the pages query
  and accumulate, which slows workspace sync.
- In-place content edits can append and update but **cannot remove or reorder** body nodes,
  and updating content leaves the old statements in the calculation, so every variable ends
  up defined twice and the page nulls out. To genuinely replace a page's content, delete the
  page and re-create it.
- Do not rely on visibility flags to hide a block. Identical MDX has imported hidden on some
  pages and visible on others.
- A traffic light must sit one hop from the block that computes its input. A chip whose
  formula reads a variable derived in a later block resolves to null.
- `insertMDXContent` creates the calculation statements and sets their titles from the
  MDX `name` attribute. A separate `createOrUpdateCalculation` is not needed to make a
  page compute.
- Client-minted UUIDs are accepted for page and statement ids, so pages you create
  this way have UUID ids while platform-created pages have 21-character nanoids.
  Nothing depends on the shape, but it is how you tell them apart in a workspace.
