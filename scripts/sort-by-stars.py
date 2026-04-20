#!/usr/bin/env python3
"""Sort each section's table in README.md by GitHub star count (descending).

Repos with fewer than MIN_STARS (default 10) are relegated to the bottom of
their section, after all >=10-star entries, preserving the same per-row format.

Star counts are fetched via `gh repo view OWNER/REPO --json stargazerCount`.
Results are cached in .star-cache.json next to this script.

Usage:
    python3 scripts/sort-by-stars.py            # sort in place
    python3 scripts/sort-by-stars.py --dry-run  # print planned order only
    python3 scripts/sort-by-stars.py --refresh  # ignore cache, refetch all
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MIN_STARS = 10
REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
CACHE = Path(__file__).resolve().parent / ".star-cache.json"

SLUG_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)")
SECTION_RE = re.compile(r"^## (.+)$")
ROW_RE = re.compile(r"^\| \[.+\]\(https://github\.com/[\w.-]+/[\w.-]+\).*\|$")


def load_cache() -> dict[str, int]:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    return {}


def save_cache(cache: dict[str, int]) -> None:
    CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True))


def fetch_stars(slug: str) -> int:
    try:
        out = subprocess.run(
            ["gh", "repo", "view", slug, "--json", "stargazerCount"],
            capture_output=True, text=True, check=True, timeout=20,
        )
        return int(json.loads(out.stdout)["stargazerCount"])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyError, ValueError):
        print(f"  ! could not fetch stars for {slug}", file=sys.stderr)
        return 0


def slug_from_row(row: str) -> str | None:
    m = SLUG_RE.search(row)
    return m.group(1).rstrip(".") if m else None


def sort_section(rows: list[str], cache: dict[str, int], refresh: bool) -> list[str]:
    """Return rows sorted by stars desc, with <MIN_STARS relegated to bottom."""
    keyed = []
    for row in rows:
        slug = slug_from_row(row)
        if slug is None:
            keyed.append((row, -1, False))
            continue
        if refresh or slug not in cache:
            cache[slug] = fetch_stars(slug)
            print(f"  {slug}: {cache[slug]}")
        stars = cache[slug]
        keyed.append((row, stars, stars >= MIN_STARS))
    # Sort: primary key — top tier (>=MIN_STARS) first, secondary — stars desc
    keyed.sort(key=lambda t: (0 if t[2] else 1, -t[1]))
    return [r for r, _, _ in keyed]


def process(dry_run: bool, refresh: bool) -> None:
    cache = {} if refresh else load_cache()
    lines = README.read_text().splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if SECTION_RE.match(line) and line != "## Contents":
            section = line[3:].strip()
            # Find the table within this section (ends at next ## or EOF)
            j = i + 1
            table_start = None
            while j < len(lines) and not lines[j].startswith("## "):
                if lines[j].startswith("| Project |"):
                    table_start = j
                    break
                j += 1
            if table_start is None:
                i += 1
                continue
            # Emit lines up to and including the header + separator
            for k in range(i + 1, table_start + 2):
                out.append(lines[k])
            # Collect data rows
            k = table_start + 2
            data_rows: list[str] = []
            while k < len(lines) and ROW_RE.match(lines[k]):
                data_rows.append(lines[k])
                k += 1
            print(f"[{section}] {len(data_rows)} rows")
            sorted_rows = sort_section(data_rows, cache, refresh)
            out.extend(sorted_rows)
            i = k
            continue
        i += 1

    save_cache(cache)
    new = "\n".join(out) + ("\n" if README.read_text().endswith("\n") else "")
    if dry_run:
        print("\n--- dry run; not writing ---")
        return
    if new != README.read_text():
        README.write_text(new)
        print(f"\nWrote {README}")
    else:
        print("\nNo changes.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--refresh", action="store_true", help="ignore cache")
    args = p.parse_args()
    process(args.dry_run, args.refresh)


if __name__ == "__main__":
    main()
