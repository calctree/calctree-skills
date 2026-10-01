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
- Statement titles
- Page references
- Workspace templates
- The page tree, folders and copies: `pageTree`, `movePageNode`, `addFolderNode`,
  `deleteFolderNode`, `restoreFolderNode`, `duplicatePageIntoWorkspace`
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
- The response is capped at about 6 MB (6291556 bytes). Every module-level Python name
  is returned, so large arrays left at module level make every call on the page fail
  with "Response payload size exceeded maximum allowed payload size". `del` them in the
  cell.

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
accumulate. For the tree as the sidebar shows it, use `pageTree`.

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

Soft delete, as in the app: the page is tombstoned (`deletedAt`) and goes to the Trash, and
`page(workspaceId, id)` then returns `null`; `page(workspaceId, id, deleted: true)` returns the
tombstone. It deletes only that page, not its sub-pages (the app deletes the whole branch), so
delete children first.

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

## Page references

A page reference is a live, parameterised call into another page's calculation. Write it in
the MDX you send to `insertMDXContent`, as either a `<PageReference>` (renders a card) or a
`<Node engine="calcSource">` (renders nothing). Both create one statement, counted in
`statementsCreated`. SKILL.md § 11 has the rules.

```mdx
<PageReference name="Shear via template" codeTitle="Shear_Check" templateId="<templateId>">
<Input name="d_eff" value="d_c" />
</PageReference>
```

````mdx
<Node name="Shear_Check" engine="calcSource">
```
{"scope": {}, "codeTitle": "Shear_Check", "calculationId": "<referenced page id>",
 "revisionId": "<its calculation revisionId>", "inputs": {"d_eff": "d_c"}}
```
</Node>
````

Read results as `<codeTitle>.<name>`, for example `Shear_Check.v_Rd_c`. The `revisionId`
for the `<Node>` form comes from the referenced page's `calculation` query
(`calculation(...) { revisionId }`).

### Snapshot references (older form)

A snapshot is a point-in-time copy of the source page's computed values, written onto the
target page as a `multiline_mathjs` statement whose object carries a metadata key:

```
alias = {
  "span": 8 m,
  "M_max": 360 kN m,
  "__ct_meta": {"sourcePageId":"...","sourcePageTitle":"...","sourceWorkspaceId":"...","importedAt":"2026-08-21T07:38:59.586Z"}
}
```

The `__ct_meta` key is what promotes it into a source-linked page reference rather than a
plain block. The alias derives from the source title with every non-word character replaced
by `_`. Values are re-serialised to mathjs source (`{"mathjs":"Unit","value":8,"unit":"m"}`
becomes `8 m`) so downstream formulas can consume them. A snapshot does not re-run and takes
no inputs; prefer a page reference.

## Workspace templates

### createWorkspaceTemplate

```graphql
mutation($workspaceId: ID, $input: CreateWorkspaceTemplateInput!) {
  createWorkspaceTemplate(workspaceId: $workspaceId, input: $input) { id }
}
```

```json
{"workspaceId": "<ws>",
 "input": {"id": "<your id>", "name": "Shear check", "description": "...",
           "tags": ["discipline:structural", "design-type:check"],
           "content": "<the page's MDX>", "source": "workspace", "sourceId": "<pageId>"}}
```

With `sourceId` this also publishes v1. Do not send `versionId`, `revisionId` or
`docContentVersion`: send any one and the server demands all three.

### updateWorkspaceTemplate, deleteWorkspaceTemplate

```graphql
mutation($workspaceId: ID, $id: ID!, $input: UpdateWorkspaceTemplateInput!) {
  updateWorkspaceTemplate(workspaceId: $workspaceId, id: $id, input: $input) { id }
}
mutation($workspaceId: ID, $id: ID!) {
  deleteWorkspaceTemplate(workspaceId: $workspaceId, id: $id) { id }
}
```

`UpdateWorkspaceTemplateInput` is `{name, description, tags, content}`, all optional. These
return correlation metadata; the change arrives over the sync subscription.

### Reading templates

```graphql
query($workspaceId: ID!, $first: Int, $after: ID) {
  workspaceTemplates(workspaceId: $workspaceId, first: $first, after: $after) { id name sourceId latestVersionId }
}
query($workspaceId: ID!, $pageId: ID!) {
  pageTemplates(workspaceId: $workspaceId, pageId: $pageId) { templateId name latestVersionId }
}
```

`workspaceTemplates` pages by `id` (pass the last row's `id` as `after`), capped at 100 per
page. `workspaceTemplate(workspaceId, id)` fetches one. A template whose `latestVersionId` is null has no published
version and cannot be referenced; `pageTemplates` gives the `templateId` for a page.

## The page tree, folders and copies

### pageTree: the tree as the sidebar shows it

```graphql
query($workspaceId: ID!) {
  pageTree(workspaceId: $workspaceId) { tree }
}
```

`tree` is JSON: page and folder nodes. A trashed folder is flagged `isDeleted: true`; a
deleted page keeps its node, and is deleted when `page(workspaceId, id)` returns `null`. Use the
tree for structure (what sits where) and `page` for existence.

### movePageNode

```graphql
mutation($workspaceId: ID!, $input: MovePageNodeInput!) {
  movePageNode(workspaceId: $workspaceId, input: $input) { previousParentId newParentId }
}
```

```json
{"workspaceId": "<ws>",
 "input": {"pageId": "<pageId>", "placement": {"parentId": "<page or folder id>"}}}
```

`placement` also takes `beforeId` and `afterId` for ordering; `input` takes an optional
`expectedParentId`.

### addFolderNode

```graphql
mutation($workspaceId: ID!, $input: AddFolderNodeInput!) {
  addFolderNode(workspaceId: $workspaceId, input: $input) { folderId }
}
```

```json
{"workspaceId": "<ws>", "input": {"folderId": "<your id>", "title": "Wind cases", "parentId": "<optional>"}}
```

A folder id is a valid `parentId` for `createPageSync` and `addPageNode`.

### deleteFolderNode, restoreFolderNode

```graphql
mutation($workspaceId: ID!, $input: DeleteFolderNodeInput!) {
  deleteFolderNode(workspaceId: $workspaceId, input: $input) { folderId }
}
mutation($workspaceId: ID!, $input: RestoreFolderNodeInput!) {
  restoreFolderNode(workspaceId: $workspaceId, input: $input) { folderId }
}
```

```json
{"workspaceId": "<ws>", "input": {"folderId": "<folderId>", "keepChildren": false, "deletedDate": "2026-09-30T00:00:00.000Z"}}
{"workspaceId": "<ws>", "input": {"folderId": "<folderId>"}}
```

With `keepChildren: false` the folder goes to Trash with the pages inside it. This is the
clean way to delete pages: move them into a temporary folder, then delete the folder.

### duplicatePageIntoWorkspace

```graphql
mutation($sourceWorkspaceId: ID!, $sourcePageId: ID!, $newPageId: ID!, $targetWorkspaceId: ID!, $parentPageId: ID) {
  duplicatePageIntoWorkspace(sourceWorkspaceId: $sourceWorkspaceId, sourcePageId: $sourcePageId,
                             newPageId: $newPageId, targetWorkspaceId: $targetWorkspaceId,
                             parentPageId: $parentPageId) {
    id title workspaceId
  }
}
```

An exact copy of the page (content, statements, charts) under the id you supply. To change a
copy's inputs, rewrite the input statement with `createOrUpdateCalculation`, reusing its
existing `statementId`. `duplicateFolderIntoWorkspace(sourceWorkspaceId, sourceFolderId,
newFolderId, targetWorkspaceId, parentFolderId)` does the same for a folder.

## In-place edits

Content edits can append and update but **cannot remove or reorder** body nodes, and
updating content leaves the old statements in the calculation — so every variable
ends up defined twice and the page nulls out. To genuinely replace a page's content,
delete the page and create it again.
