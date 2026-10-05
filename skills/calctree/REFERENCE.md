# CalcTree GraphQL reference

Every operation the skill needs, with its variables and response shape. This file
exists so you can drive CalcTree with nothing but an HTTP client — no CalcTree
libraries, no Node, no Python. `scripts/calctree_api.py` is a convenience wrapper
around exactly these calls; if you can run it, prefer it, and read this when you
need the wire format.

- **Endpoint:** `POST https://graph.calctree.com/graphql`
- **Headers:** `Content-Type: application/json`, `x-api-key: <your key>`
- **Body:** `{"query": "<document>", "variables": { ... }}`

One API key covers every call below. An invalid or empty key comes back as a bare
`"Unexpected error."` with no 401 and no mention of auth — if you see that, check
the key before debugging anything else.

## Contents

- Execute: `simpleCalculate`
- The write path, in order
- Ids
- Reads: `pages`, `page` + `pageContent`, `calculation`, `pageMDX`
- Writes: `createPageSync`, `addPageNode`, `insertMDXContent`, `createOrUpdateCalculation`, `deletePage`
- Statement titles, and the two traps
- Templates: `workspaceTemplates`, `pageTemplates`, `workspaceTemplate`, `workspaceTemplateVersion(s)`
- Cross-page references: live `<PageReference>`, and the `__ct_meta` snapshot
- In-place edits

## Execute: simpleCalculate

Run a page's calculation graph with optional input overrides. Read-only — does not
modify the page.

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

`calculationId` equals the page id. `scope` entries are MathJS-serialised strings.

The response `statements` array contains every statement with its recomputed
`namedValues`. The `scope` array has every resolved variable with its `type` and any
`artifacts` (e.g. plot images).

**Limitations:**
- Dataset variables (VLOOKUP) are **not** in the scope — they always report
  "Undefined symbol" even when the dataset works in the UI.
- Python statement outputs may not appear in the simplified scope.

## The write path, in order

Creating a page that renders and computes is three calls. All three are required.

1. `createPageSync` — makes the page
2. `addPageNode` — registers it in the page tree, or it is orphaned and invisible
3. `insertMDXContent` — puts prose and calculation blocks in, persists the statements,
   and sets statement titles from the MDX `name` attribute

## Ids

Client-minted ids are accepted for pages and statements; a UUID is fine.
Platform-generated ids are 21-character nanoids, so id shape is how you tell an
API-created page from a UI-created one. Nothing depends on it.

The **calculation id equals the page id**. There is no separate calculation to create.

## Reads

### pages — list a workspace

```graphql
query($workspaceId: ID!) {
  pages(workspaceId: $workspaceId) { id title }
}
```

Deleting a page is a **soft** delete, so trashed pages still come back here and
accumulate.

### page + pageContent — title and body

```graphql
query($workspaceId: ID!, $pageId: ID!) {
  page(workspaceId: $workspaceId, id: $pageId) { id title }
  pageContent(workspaceId: $workspaceId, pageId: $pageId) { content }
}
```

### calculation — the graph and its computed values

This is how you verify a page. `revisionId` is `"~"` for latest.

```graphql
query($workspaceId: ID!, $calculationId: ID!, $revisionId: ID!) {
  calculation(workspaceId: $workspaceId, calculationId: $calculationId, revisionId: $revisionId) {
    statements {
      statementId
      title
      engine
      formula
      namedValues { name value }
      errors
    }
  }
}
```

Variables: `{"workspaceId": "...", "calculationId": "<pageId>", "revisionId": "~"}`

`namedValues[].value` arrives **JSON-encoded as a string**, MathJS-serialised:

```json
"{\"mathjs\":\"Unit\",\"value\":8,\"unit\":\"m\",\"fixPrefix\":false}"
```

So parse it, then read `.value` and `.unit`. Plain numbers and strings come through
as themselves.

**Why `revisionId` is `"~"`:** revision ids are KSUIDs, and `~` sorts above every
base62 character, so it always means latest. Hex-looking values (`"ffffffff"`)
appear in older documentation and answer today only because no revision id has yet
sorted above them — a KSUID beginning with a letter after `f` silently stops
matching. Do not use a hex value.

**Evaluation is asynchronous.** Settle a couple of seconds after a write before
reading, or the read comes back with zero statements, or with statements that have
no `namedValues` yet.

### pageMDX — body back as MDX

```graphql
query($workspaceId: ID!, $pageId: ID!) {
  pageMDX(workspaceId: $workspaceId, pageId: $pageId)
}
```

**Never verify a calculation with this.** MDX serialisation round-trips prose
reliably but returns calculation blocks **empty**, so a perfectly good page looks
broken. Use the `calculation` query.

## Writes

### createPageSync

```graphql
mutation($workspaceId: ID!, $input: CreatePageInput!) {
  createPageSync(workspaceId: $workspaceId, input: $input) { id title }
}
```

```json
{"workspaceId": "<ws>",
 "input": {"id": "<uuid>", "title": "Beam check", "workspaceId": "<ws>", "parentId": "<optional>"}}
```

`workspaceId` appears both at the top level and inside `input`.

### addPageNode — required

```graphql
mutation($workspaceId: ID!, $input: AddPageNodeInput!) {
  addPageNode(workspaceId: $workspaceId, input: $input) { newPageId parentId }
}
```

```json
{"workspaceId": "<ws>", "input": {"pageId": "<pageId>", "parentId": "<optional>"}}
```

Skip this and the page exists but is invisible in the UI.

### insertMDXContent

```graphql
mutation($workspaceId: ID!, $pageId: ID!, $content: String!, $position: LocationInput!) {
  insertMDXContent(workspaceId: $workspaceId, pageId: $pageId, content: $content, position: $position) {
    insertedCount
    statementsCreated
    warnings
  }
}
```

```json
{"workspaceId": "<ws>", "pageId": "<pageId>", "content": "<mdx>", "position": {"path": [0]}}
```

`position` is a Slate location. `{"path": [0]}` prepends; to append, pass the
current top-level node count.

**Check `statementsCreated` against the number of calculation blocks you sent.** A
write that inserted nodes and created zero statements is a failure whatever the HTTP
status says — that is the shape the old auth bug took, and it is worth keeping as a
tripwire.

Prose and calculation blocks both go through here, and the statements **do** evaluate
server-side. A separate `createOrUpdateCalculation` is not needed to make a page
compute.

**`warnings` must be empty.** It lists what the insert skipped. Today that means only
`<PageReference>` tags the server refused (template not visible here, never
published, unknown version). Such a block is still placed but creates no statement,
so a non-empty `warnings` together with a lower `statementsCreated` is a failure.

If the MDX deserialises to **no body nodes at all** (for example, only `<Python>`
blocks), the server returns `0/0` and writes no statements. Include a heading or
paragraph.

### createOrUpdateCalculation

Writes the calculation graph only — no page body. Use it for graph-only writes, for
cross-page references, and to set titles.

```graphql
mutation($workspaceId: ID!, $calculationId: ID!, $withStatements: [CreateStatementInput!]!) {
  createOrUpdateCalculation(workspaceId: $workspaceId, calculationId: $calculationId, withStatements: $withStatements) {
    calculationId
    revisionId
  }
}
```

```json
{"workspaceId": "<ws>", "calculationId": "<pageId>",
 "withStatements": [{"statementId": "<uuid>", "title": "Beam moment",
                     "engine": "multiline_mathjs",
                     "formula": "span = 8 m\nload = 45 kN / m\nM_max = load * span^2 / 8"}]}
```

`engine` is one of `mathjs`, `multiline_mathjs`, `python`, `excel`, `dataset`,
`connection`. All statements in a calculation share one scope.

Reusing an existing `statementId` **updates in place**. This upsert never deletes,
so a wrong id leaves the old statement live and evaluating alongside the new one.

The returned `revisionId` can be `null` even on success. Do not depend on it; read
back with `"~"`.

Unlike `insertMDXContent`, this **does** set titles.

### createPdfReport

```graphql
mutation($workspaceId: ID!, $input: CreatePdfReportInput!) {
  createPdfReport(workspaceId: $workspaceId, input: $input) {
    id
    reportStatus
  }
}
```

`reportStatus` is `"pending"` on creation. See SKILL.md § 4 for the full input shape.

### pdfReport

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

Poll until `reportStatus` is `"ready"` (gives `signedUrl`) or `"error"` (gives
`errorMessage`). Poll interval: 3–5 seconds.

### deletePage

```graphql
mutation($workspaceId: ID!, $id: ID!) {
  deletePage(workspaceId: $workspaceId, id: $id) { id }
}
```

Soft delete.

### createPresignedUploadPost — CSV dataset upload

Two-step process: get a presigned S3 URL, then POST the file to it.

**Step 1: get the presigned URL**

```graphql
mutation($w: ID!, $p: ID!, $f: String!, $t: String!) {
  createPresignedUploadPost(workspaceId: $w, pageId: $p, fileName: $f, fileType: $t) {
    presignedPost { url fields }
    file { id }
  }
}
```

```json
{"w": "<workspaceId>", "p": "<pageId>", "f": "chain_catalog.csv", "t": "text/csv"}
```

**Step 2: POST to S3**

Send a `multipart/form-data` POST to `presignedPost.url`. Include every key-value
pair from `presignedPost.fields` as form fields, then the file content as a `file`
field. The S3 response is 200 or 204 with no body.

Wait at least 60 seconds after upload before inserting MDX that uses `VLOOKUP`
against the dataset.

## Statement titles

`insertMDXContent` now sets statement titles from the MDX `name` attribute
automatically. No separate `createOrUpdateCalculation` call is needed for titles.
Verified on prod 2026-08-24.

## Templates

All of these are reads, and an API key reaches them as a member of the workspace. **There is
no template search query.** Page through `workspaceTemplates` and filter on `name`,
`description` and `tags` yourself.

### workspaceTemplates: list what this workspace can see

The workspace's own templates plus every built-in, with deleted ones excluded, in `id` order.

```graphql
query($workspaceId: ID!, $first: Int, $after: ID) {
  workspaceTemplates(workspaceId: $workspaceId, first: $first, after: $after) {
    id name description tags source sourceId latestVersionId
    workspace { id }
  }
}
```

```json
{"workspaceId": "<ws>", "first": 100}
```

To page, pass the last row's `id` as `after`, and **keep going until a page comes back
empty**. `first` is capped at 100 server-side, so a short page does not mean you have reached
the end. Leave `content` out of the selection while listing, because every row carries its
full MDX.

- `workspace` is null for a built-in. Use it to tell built-ins apart, not `source`.
- `latestVersionId` null means the template has never been published, so it **cannot be
  referenced** through the API (see below).

### pageTemplates: templates saved from a known page

When you have a page id and want the `templateId` a `<PageReference>` needs:

```graphql
query($workspaceId: ID!, $pageId: ID!) {
  pageTemplates(workspaceId: $workspaceId, pageId: $pageId) {
    templateId name latestVersion latestVersionId
    workspace { id }
  }
}
```

Lists the workspace's own templates first, then built-ins. `latestVersion` is the number
to write as `templateVersion`, and null means never published. An empty list means the page
was never saved as a template, or is not a live page in this workspace.

### workspaceTemplate, workspaceTemplateVersion, workspaceTemplateVersions

```graphql
query($workspaceId: ID!, $id: ID!) {
  workspaceTemplate(workspaceId: $workspaceId, id: $id) {
    id name description tags sourceId latestVersionId workspace { id }
  }
}
```

```graphql
query($workspaceId: ID!, $id: ID!) {
  workspaceTemplateVersion(workspaceId: $workspaceId, id: $id) {
    id templateId version nameAtPublish calculationId revisionId content
  }
}
```

```graphql
query($workspaceId: ID!, $templateId: ID!) {
  workspaceTemplateVersions(workspaceId: $workspaceId, templateId: $templateId, first: 20) {
    id version nameAtPublish createdAt
  }
}
```

- `workspaceTemplate` returns null for a template in another workspace, one that does not
  exist, or one that was deleted.
- A version's `content` is the published MDX. It is what you copy when you want an editable
  copy rather than a reference. Fetch it by `latestVersionId`, not from
  `workspaceTemplate.content`, which can drift from what was published.
- A version's `calculationId` and `revisionId` are the exact calculation a reference pins.
  Pass them to the `calculation` query to read its input names and outputs.
- Versions are newest first, capped at 100.

## Cross-page references

### Live: `<PageReference>` through insertMDXContent

```
<PageReference name="Beam check" codeTitle="Beam_Check" templateId="<templateId>">
<Input name="L" value="span" />
<Input name="w" value="udl * 1.5" />
</PageReference>
```

When you insert, the server resolves the template to a pinned `(calculationId,
revisionId)` and creates a `calcSource` statement. Outputs are read downstream as
`Beam_Check.<output>`. It resolves only:

- a template visible to this workspace (its own, or a built-in) that is backed by a page,
- at its latest **published** version, or at `templateVersion="3"`/`"v3"` if you give one.

A template that was never published, an unparseable or unknown version, a missing template
or one with no source page each produce a `warnings` entry and no statement. A tag with no
`templateId` is dropped outright. The server applies no feature flag to this path.

### Snapshot: the `__ct_meta` object

A snapshot is a point-in-time copy of the source page's computed values,
written onto the target page as a `multiline_mathjs` statement whose object carries
a metadata key:

```
alias = {
  "span": 8 m,
  "M_max": 360 kN m,
  "__ct_meta": {"sourcePageId":"...","sourcePageTitle":"...","sourceWorkspaceId":"...","importedAt":"2026-08-21T07:38:59.586Z"}
}
```

The `__ct_meta` key is what promotes it into a real source-linked page reference
rather than a plain block. The alias derives from the source title with every
non-word character replaced by `_`. Values are re-serialised to mathjs source
(`{"mathjs":"Unit","value":8,"unit":"m"}` becomes `8 m`) so downstream formulas can
consume them.

Summary and roll-up pages should reference upstream results this way rather than
recomputing them.

## In-place edits

Content edits can append and update but **cannot remove or reorder** body nodes, and
updating content leaves the old statements in the calculation — so every variable
ends up defined twice and the page nulls out. To genuinely replace a page's content,
delete the page and create it again.
