#!/usr/bin/env bash
# Extracts the body of one version's section from CHANGELOG.md (Keep a
# Changelog format: "## [X.Y.Z] - date" headings), for use as a release
# description. Prints to stdout; exits 1 if the version has no section.
set -euo pipefail

version="${1:?usage: changelog_section.sh <version> [changelog-file]}"
changelog="${2:-CHANGELOG.md}"

awk -v ver="$version" '
  /^## \[/ {
    if (found) exit
    if ($0 == "## [" ver "]" || $0 ~ ("^## \\[" ver "\\][ ]")) { found = 1 }
    next
  }
  found { lines[++n] = $0 }
  END {
    start = 1
    end = n
    while (start <= n && lines[start] ~ /^[[:space:]]*$/) start++
    while (end >= 1 && lines[end] ~ /^[[:space:]]*$/) end--
    if (start > end) exit 1
    for (i = start; i <= end; i++) print lines[i]
  }
' "$changelog"
