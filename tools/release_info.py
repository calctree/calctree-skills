#!/usr/bin/env python3
"""
Version and release-notes helper for the release workflow and CI.

The version lives in .claude-plugin/plugin.json. skills/calctree/VERSION must match
it, because that file ships in the zip and is what the skill's update check compares
against. This script is the one place that checks the two agree.

Usage:
  python3 tools/release_info.py check          fail if plugin.json and VERSION disagree
  python3 tools/release_info.py version        print the version (after checking)
  python3 tools/release_info.py notes [ver]    print the CHANGELOG.md section for a
                                               version; exit 1 if there is none
"""
from __future__ import annotations

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_JSON = os.path.join(REPO, ".claude-plugin", "plugin.json")
CHANGELOG = os.path.join(REPO, "CHANGELOG.md")


def version_file(skill: str = "calctree") -> str:
    return os.path.join(REPO, "skills", skill, "VERSION")


def plugin_version() -> str:
    with open(PLUGIN_JSON, encoding="utf-8") as f:
        return json.load(f)["version"].strip()


def skill_version(skill: str = "calctree") -> str:
    with open(version_file(skill), encoding="utf-8") as f:
        return f.read().strip()


def check(skill: str = "calctree") -> str:
    """Return the version, or exit with a message if the two sources disagree."""
    p, s = plugin_version(), skill_version(skill)
    if not re.fullmatch(r"\d+\.\d+\.\d+", p):
        sys.exit(f"plugin.json version {p!r} is not MAJOR.MINOR.PATCH")
    if p != s:
        sys.exit(f"version mismatch: .claude-plugin/plugin.json says {p}, "
                 f"skills/{skill}/VERSION says {s}. Set both to the same value.")
    return p


def changelog_section(version: str) -> str | None:
    """The body under '## <version>' (or '## [<version>]') up to the next '## '."""
    if not os.path.isfile(CHANGELOG):
        return None
    text = open(CHANGELOG, encoding="utf-8").read()
    head = re.compile(rf"^##\s+\[?v?{re.escape(version)}\]?(?:\s|$).*$", re.M)
    m = head.search(text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"^##\s", rest, re.M)
    body = (rest[:nxt.start()] if nxt else rest).strip()
    return body or None


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "check":
        print(f"version {check()} (plugin.json and VERSION agree)")
        if changelog_section(plugin_version()) is None:
            # Not fatal: the release falls back to generated notes.
            print(f"::warning::CHANGELOG.md has no '## {plugin_version()}' section")
    elif cmd == "version":
        print(check())
    elif cmd == "notes":
        v = argv[2] if len(argv) > 2 else check()
        body = changelog_section(v)
        if body is None:
            print(f"no CHANGELOG.md section for {v}", file=sys.stderr)
            return 1
        print(body)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
