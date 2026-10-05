#!/usr/bin/env python3
"""
Build the distributable skill archive.

One source directory, packaged for every surface that takes a zip:

  - claude.ai / Claude desktop / Cowork: Settings > Features > upload
  - Claude API: POST /v1/skills

The zip contains the SKILL FOLDER as its root entry, which is what those uploads
require — files loose at the zip root are rejected.

Deliberately excluded: the TypeScript primitives (they need Node plus tsx, which is
not available in the claude.ai sandbox) and anything internal.

Usage:  python3 tools/package_skill.py [--out dist] [--skill <name>]
"""
from __future__ import annotations

import argparse
import os
import sys
import zipfile

from release_info import check as check_versions

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SKILL = "calctree"

# Only these ship. Anything not listed is internal by default, which is the safe
# direction for a repo that also holds working notes.
INCLUDE = [
    "SKILL.md",
    "VERSION",
    "REFERENCE.md",
    "scripts/calctree_api.py",
    "examples/smoke_two_page.py",
]


def build(skill: str, out_dir: str) -> str:
    src = os.path.join(REPO, "skills", skill)
    if not os.path.isdir(src):
        sys.exit(f"no such skill directory: {src}")

    missing = [f for f in INCLUDE if not os.path.isfile(os.path.join(src, f))]
    if missing:
        sys.exit(f"missing from {skill}: {', '.join(missing)}")

    # A SKILL.md without frontmatter will not be discovered, so fail loudly here
    # rather than shipping a zip that silently does nothing.
    head = open(os.path.join(src, "SKILL.md"), encoding="utf-8").read(4096)
    if not head.startswith("---") or "name:" not in head or "description:" not in head:
        sys.exit("SKILL.md needs YAML frontmatter with 'name' and 'description'")

    # VERSION ships so the skill can compare itself with the copy on main. It must
    # match plugin.json, or the update check would nag about a version that is not out.
    if skill == DEFAULT_SKILL:
        version = check_versions(skill)
        print(f"version {version}")

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{skill}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in INCLUDE:
            z.write(os.path.join(src, rel), arcname=os.path.join(skill, rel))

    size = os.path.getsize(path)
    print(f"{path}  ({size / 1024:.1f} KiB)")
    with zipfile.ZipFile(path) as z:
        for n in sorted(z.namelist()):
            print(f"  {n}")
    print(f"\nRoot entry is '{skill}/', which is what the claude.ai upload expects.")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "dist"))
    ap.add_argument("--skill", default=DEFAULT_SKILL)
    args = ap.parse_args()
    build(args.skill, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
