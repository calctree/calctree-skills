---
name: building-calctree-calculations
description: Build and read CalcTree calculation pages programmatically via the GraphQL API. Use when creating engineering calculations, inserting MDX content with live formulas, reading computed values back, or linking pages together. Covers auth, the write path, MathJS and Python statements, and the rules that silently break pages.
---

# CalcTree

CalcTree is an engineering calculation platform. A **page** holds prose plus calculation
blocks; the blocks form a **calculation graph** that evaluates server-side, with real units.
This skill is how an AI agent drives it from outside the platform.

Everything here is verified working against the live API. Treat it as settled.

## Bundled code

The primitives implement everything below. Prefer running them over re-writing the calls.

- `scripts/calctree-api.ts` — page creation with tree registration, MDX insert, calculation
  writes, page-context reads, cross-page references. **Read as reference** when you need the
  exact GraphQL shape; **import and call** when driving.
- `scripts/auth.ts` — `ensureBearer()`. Requires `CALCTREE_LOGIN_EMAIL` and
  `CALCTREE_LOGIN_PASSWORD`, or a pre-set `CALCTREE_BEARER`.
- `examples/smoke-two-page.ts` — **run this first** to confirm your credentials and endpoint
  work end to end. It creates two linked pages, reads the computed values back, and prints the
  page URLs:

  ```bash
  npx tsx examples/smoke-two-page.ts <workspaceId>
  ```

Requires `tsx` (or any TypeScript-aware runner). No other dependencies.

## 1. Auth: use Bearer, not an API key

Endpoint: `https://graph.calctree.com/graphql`, header `Authorization: Bearer <jwt>`.

Mint a token with `POST https://api.calctree.com/api/auth/login` with `{email, password}`,
which returns `{accessToken}`.

**Do not use `x-api-key` for content writes.** The API key does not carry through to the
calculation service, so `insertMDXContent` creates the body node while the statement is
rejected: you get a page that looks correct with empty calculation blocks and no error.
Bearer creates the node and the statement together.

This is a known platform limitation rather than the intended design. When it is fixed, the API
key becomes the normal path for every call and this section changes accordingly. Until then, the API key is
fine for reads and for every other mutation; only `insertMDXContent` and
`createOrUpdateCalculation` need a login-minted Bearer. Either way, **check the response**: a
write that returns zero created statements has failed, whatever the HTTP status says.

## 2. The write path

Two calls, in order:

1. **Create the page and register it in the page tree.** Both are required. A page that
   exists but is not in the tree is orphaned and invisible in the UI. Client-minted ids are
   accepted; platform-generated ids are 21-character nanoids.
2. **`insertMDXContent(workspaceId, pageId, mdx, position)`** returns
   `{insertedCount, statementsCreated}`. Prose and inline calculation blocks both go through
   here. Always check `statementsCreated` matches what you sent.

For calculation-graph-only writes with no body node, use
`createOrUpdateCalculation(workspaceId, pageId, statements[])`, where each statement is
`{statementId?, title, engine, formula}` and `engine` is one of `mathjs`,
`multiline_mathjs`, `python`, `excel`, `dataset`, `connection`. Note that the calculation id
equals the page id.

## 3. MDX calculation syntax

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

## 4. Reading back and verifying

- **Settle about two seconds after a write before reading.** Evaluation is asynchronous
  server-side, and an immediate read can return zero statements.
- Read the graph and its values with the page-context query, which returns statements with
  `namedValues` and `errors`. Values arrive MathJS-serialised, for example
  `{mathjs: "Unit", value: 8, unit: "m"}`.
- **Do not verify calculations by reading the page back as MDX.** MDX serialisation
  round-trips prose reliably but returns calculation blocks empty, so a correct page looks
  broken. Use the page-context query.
- Calculations really do evaluate server-side. No browser is needed.

## 5. Formula rules

Same engine as the in-app editor:

- Assignment syntax always: `variable = expression`.
- Units on inputs (`load = 5 kN`); calculated values inherit them, so do not re-declare.
- `equalText()` for string comparison, not `==`. Word operators: `and`, `or`, `xor`, `not`.
- Double-quote strings.
- **Avoid variable names that collide with unit abbreviations** (`N`, `V`, `Pa`, `M`, `mm`,
  `m`, `s`, `kg`, `K`, `A`, `g`, `h`, `d`, `J`). Use `M_max`, not `M`. A variable named `mm`
  shadows the millimetre unit and nulls every later conversion on the page.
- Within one `multiline_mathjs` formula, define a variable before using it. Across separate
  statements order does not matter: it is a dependency graph.

### Selecting on a string

MathJS will not do string equality inside a conditional — `_choice == "Option A" ? 1 : 2` fails with
"Cannot convert ... to a number". Look the value up by position instead:

```
choice_index = MATCH(_choice, ["Option A", "Option B", "Option C"], 0)
chosen_value = INDEX([0.05, 0.3, 1.0], choice_index)
```

This is the normal way to drive numbers from a `<SelectInput>` whose `ctselect` options are
human-readable labels.

## 6. Writing pages that read correctly

The API will happily create a page that computes but presents badly. These are the ones that
bite:

- **Let units flow.** A dimensional value carries its unit and prints it, so never write the
  unit into a column heading and never strip a value to a bare number to do so. Convert for
  display with `to` (`As_r = (round(As / (1 mm^2), 0) * (1 mm^2)) to mm^2`); without the `to`
  MathJS auto-rescales and mm² becomes ha. `round()` on a unitful value must strip the unit
  first: `round(X / (1 mm), 3)`.
- **Round for display in a separate copy**, never on the value the rest of the calculation
  consumes.
- **A pass/fail check is a `[boolean, label]` pair**, not a bare boolean and never a plain
  string ternary. Write `within_limits = [util <= 1, util <= 1 ? "PASS" : "FAIL"]`. The chip
  takes its colour from element 0 and its text from element 1.
  - `check = util <= 1 ? "PASS" : "FAIL"` alone is always truthy, so the chip renders green
    whatever the result. In the pair form the string is a label sitting beside a boolean, so
    it does not have that problem.
  - A bare `within_limits = util <= 1` renders a chip with an **empty label**; any `true` or
    `false` you see next to it is the separate value read-out, not the chip text.
  - Define it in a `<TrafficLights>` element, not as a line in an `EquationBlock` — an
    EquationBlock renders the check as an unreadable piecewise brace matrix.
  - Show it in a table as a mention of the pair:
    `<Mention key="within_limits" value="within_limits" showTitle="false" showValue="true" variableType="trafficlights" />`.
    A `<TrafficLights>` component inside a plain pipe-table cell is dropped; cells only hold
    components inside a `<RichTable>`.
  - A check must sit one hop from the block computing its input: a chip reading a variable
    derived in a later block resolves to null.
- **Mentions are display-only.** Do the rounding in MathJS and treat the mention as a
  read-out. A mention of a variable the page never defines renders as the word `undefined`
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

## 7. Python statements

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

### Naming inside a Python statement

**Every module-level name in the cell becomes a value on the page, including loop variables**, and a
one-letter name will shadow a MathJS unit. A drawing loop written `for t in tags:` puts `t` into page
scope as an integer, which shadows the **tonne** unit, and every downstream `... to t` then fails
with "Unexpected type of argument in function to". Because one bad line kills a whole multiline
block, the visible symptom is that a dozen unrelated values go `unevaluated` while the Python
statement itself reports success.

- Prefix throwaway names with `_`: `_row`, `_node`, `_fx`. Comprehensions have their own scope and
  are safe; a bare `for x in ...:` at module level is not.
- Spell units out in MathJS — `to tonne`, not `to t`.

Single letters that are live MathJS units and should never be module-level Python names:
`t A C F J K N T V W L l g s h d b m`, plus their prefixed forms.

## 8. The MDX component vocabulary

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

## 9. Linking pages with `<PageReference>`

Summary and roll-up pages should **reference** upstream results, not recompute them. A reference is
a live, parameterised call into another page's calculation — not a copy of its numbers.

```mdx
<PageReference name="Wind at 90 degrees" codeTitle="Wind_090_Result" templateId="<templateId>">
<Input name="qp_input" value="Site_Wind.qp_peak" />
<Input name="ref_height" value="cover_height" />
</PageReference>
```

- **Keyed on `templateId`** — the id of a saved workspace template, never a page id, revision id or
  workspace id. The referenced page must be saved as a template **with a published version**
  (section 10); without one the reference renders invisible and reports no error.
- **`codeTitle`** names the block whose content renders in the card.
- **`<Input>` children remap the module's inputs.** `name` is a variable in the referenced page;
  `value` is any MathJS expression evaluated in **this** page's scope — a bare variable, a
  unit-valued one, or an expression like `Wind_Envelope.uplift * (1 kN/m^2)`. The referenced
  calculation genuinely re-runs with those values, including any Python statements it contains.

Four behaviours worth knowing before you design a page around this:

1. **A reference returns the referenced page's whole scope**, not just the named block. Referencing
   two different blocks of the same page gives two identical payloads.
2. **The accessor is `<codeTitle>.<variable>`** — `Wind_090_Result.p_bulk_uplift`. Using the
   reference's `name` attribute instead returns `null` with type `unevaluated`, which is a silent
   and expensive mistake.
3. **One scope entry per `codeTitle` per page.** Reference the same `codeTitle` twice on one page
   and both cards render correct numbers, but only the **last** lands in scope — the first is
   unreachable from MathJS. To call one calculation several times and aggregate the results, give
   each instance its own `codeTitle`, which in practice means one sub-page per case.
4. **References nest.** A page that is itself a host can be referenced by another page, and inputs
   propagate all the way down. Chains several levels deep re-run correctly.

An older snapshot form also exists, where a statement carries the upstream values frozen alongside
a metadata key. It has no input remapping and does not re-run. Prefer `<PageReference>`.

## 10. Saving a page as a reusable template

A **workspace template** is a saved calculation your workspace can start new pages from. Three
mutations manage them, and `content` is simply the page's MDX — not a page id, not a serialised
document:

```graphql
mutation ($workspaceId: ID!, $input: CreateWorkspaceTemplateInput!) {
  createWorkspaceTemplate(workspaceId: $workspaceId, input: $input) { __typename }
}
# input: { id, name, description, tags, content, source: workspace, sourceId }
```

```graphql
mutation ($workspaceId: ID!, $id: ID!, $input: UpdateWorkspaceTemplateInput!) {
  updateWorkspaceTemplate(workspaceId: $workspaceId, id: $id, input: $input) { __typename }
}
# input: { name, description, tags, content } — all optional
```

`deleteWorkspaceTemplate(workspaceId, id)` removes one. All three return immediately with
correlation metadata; the result arrives over the sync subscription, so do not expect the updated
template in the response.

Notes that will save you time:

- **You supply `id` on create.** Generate it yourself and keep it — that id is how you update the
  template later, and there is no lookup-by-name.
- **Update rather than delete-and-recreate.** Recreating mints a new id and orphans anything
  referencing the old one.
- **Tags are a closed vocabulary** if you want them to act as filters: `discipline:` (structural,
  geotechnical, civil, mechanical, electrical), `jurisdiction:` (aus, nz, us, uk, eu),
  `design-type:` (check, analysis, sizing, reference). Any other tag is kept as a freeform tag and
  matches no filter.
- **Reading templates back.** `workspaceTemplates(workspaceId, first, after)` lists them, paged by
  `id` — pass the last row's `id` as `after` and keep going until a page comes back empty. `first`
  is capped server-side at 100 regardless of what you ask for, because every row carries its full
  MDX `content`. `workspaceTemplate(workspaceId, id)` fetches one, and
  `pageTemplates(workspaceId, pageId)` is how a caller holding only a page id finds the
  `templateId` a `<PageReference>` needs.

### Versions — the part that makes references work

A `<PageReference>` pins a **published version**, not the template row. A template with no version
cannot be referenced, and the failure is silent: the reference is created and renders nothing.

- **Creating a template from a page publishes v1 for you.** Pass `sourceId` set to the page id and
  `createWorkspaceTemplate` publishes the first version as part of the create. Do **not** also call
  `publishWorkspaceTemplateVersion` for v1 — it is refused as stale because one already exists.
- **Do not pass `versionId` on create.** Doing so also requires `revisionId` and
  `docContentVersion`, and that last one is a hash of the editor's document that an API caller
  cannot compute. Omit all three and the server pins the page's latest saved state itself.
- **`sourceId` is what makes a template publishable.** A template row created with no page behind it
  has nothing to freeze, so it can never have a version and can never be referenced. If you want a
  template to be referenceable, build it from a real page.
- **Later versions** go through `publishWorkspaceTemplateVersion`, passing `expectedLatestVersionId`
  — required in practice even when `null`, despite being typed optional.
- **Wait for the page to save.** The server pins what has been saved, so publishing immediately
  after writing content can freeze the state from before your edit. Verify by reading the version
  back rather than trusting the call returned.

## 11. Building a multi-page project

A project is a page tree, and the pages in it should call each other rather than repeat each other.
One pattern carries almost all of it:

- A **module** is a self-contained calculation that shows its full working and has sensible defaults
  of its own. It is saved as a template with a published version, and it exposes its results in a
  named block — `Wind_090_Result`, `Ballast_Result`.
- A **host** owns the project's inputs and *calls* modules with them through `<PageReference>`,
  then reads their results back with `<codeTitle>.<variable>` and takes the envelope, the verdict
  or the summary.

Hosts nest, so a summary page can call a sub-summary that calls three modules, and the project's
inputs propagate all the way down. Set the geometry once on the top page and everything below
re-runs — including any Python or finite element work inside the modules.

**Section 9's rule 3 shapes the tree.** Because only one scope entry survives per `codeTitle`, the
same module cannot be called several times on one page and then aggregated. When a calculation has
to run once per case — per wind direction, per load combination, per storey — give each case its
own sub-page with its own result block name, and have the summary reference those. That is why a
well-built project has more small pages than you would first expect, and it is also what makes each
case independently reviewable.

### The page tree

`createPage`/`createPageSync` sets a page's own parent pointer but does **not** file it in the tree.
Call `addPageNode(workspaceId, { pageId, parentId })` as well, or the page exists, computes and is
reachable by URL while being invisible in the sidebar.

Ordering and restructuring go through `movePageNode(workspaceId, { pageId, placement, expectedParentId })`,
where `placement` is `{ parentId, beforeId, afterId }`. Prefer it to rewriting the whole tree.

Folders exist as first-class nodes — `addFolderNode`, `renameFolderNode`, `moveFolderNode`,
`deleteFolderNode` — so a grouping level can be a real folder. The alternative is to use an ordinary
page as the group header, which costs nothing extra and lets the group carry an index table
explaining what is inside it. Both are valid; pick one and be consistent.

To start a new job from a finished project, `duplicateFolderIntoWorkspace` copies a whole folder,
including across workspaces.

## 12. Gotchas worth knowing before you start

- Deleting a page is a **soft** delete. Trashed pages still come back from the pages query
  and accumulate, which slows workspace sync. `pageSubtree` returns them too, so neither query
  tells you whether a page still exists — `page(workspaceId, id)` returning `null` does.
- In-place content edits can append and update but **cannot remove or reorder** body nodes,
  and updating content leaves the old statements in the calculation, so every variable ends
  up defined twice and the page nulls out. To genuinely replace a page's content, delete the
  page and re-create it.
- Do not rely on visibility flags to hide a block. Identical MDX has imported hidden on some
  pages and visible on others.
- A traffic light must sit one hop from the block that computes its input. A chip whose
  formula reads a variable derived in a later block resolves to null.
