# Changelog

Each `## <version>` section becomes the notes for release `v<version>`. The version is
the one in `.claude-plugin/plugin.json`, and `skills/calctree/VERSION` must match it.

Get the latest zip from
[releases/latest/download/calctree.zip](https://github.com/calctree/calctree-skills/releases/latest/download/calctree.zip).
In Claude Code, run `/plugin marketplace update calctree`.

## 1.1.0

Brings the skill's authoring rules in line with the CalcTree in-app AI, and adds live
template references.

- **Modern MDX syntax.** Mentions use the `mention:` link form instead of `<Mention>`,
  and EquationBlocks use a fenced body instead of `formula=`. `PythonCell` and
  `SolveBlock` are now documented, and `<Python>` is documented as the MDX path to a
  classic Python statement.
- **More authoring rules from the in-app AI:** engineering integrity, unit system by
  jurisdiction, no apostrophes or currency units in formulas, `<details>`/`<summary>`,
  column groups, RichTable and InputTable rules, and a table of deprecated tags.
- **Mention formatting.** `format` survives import. Use `decimal` only with
  `format="number"` and a `variableType`.
- **Live template references.** A new section covers when to reference a template, copy
  it, or snapshot it, plus how to find templates (the API has no search) and how to
  write and verify a `<PageReference>`. Only published templates can be referenced.
- **`calctree_api.py`:** `insertMDXContent` now returns `warnings`, and `build` fails on
  them. New `templates`, `page-templates` and `version` commands.
- **Update check.** The skill now carries a `VERSION` file. When it is already calling
  the CalcTree API, it checks once per conversation for a newer version and mentions it
  in one line.
- **Numbered releases.** Each version is published as release `v<version>`, replacing the
  single `latest` release that was recreated on every push.

## 1.0.0

First release: discover, execute and build CalcTree calculation pages through the
GraphQL API, with a standard-library Python CLI.
