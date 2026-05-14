#!/usr/bin/env bash
# Commits the latest report(s) in docs/ and pushes to GitHub Pages.
# Prints a clickable URL for the most recently modified report.
#
# Requires that you've already linked this folder to a GitHub repo
# called `well-reports` and enabled Pages (see README.md).

set -euo pipefail

cd "$(dirname "$0")/.."

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Error: not a git repo yet. See README.md step 2." >&2
  exit 1
fi

# Latest modified HTML in docs/
latest="$(ls -t docs/*.html 2>/dev/null | head -n1 || true)"
if [ -z "$latest" ]; then
  echo "No report HTML files in docs/." >&2
  exit 1
fi

filename="$(basename "$latest")"

git add docs/
if git diff --cached --quiet; then
  echo "No changes in docs/ to commit."
else
  git commit -m "Add report: $filename"
fi
git push

# Derive the GitHub Pages URL from the remote.
remote="$(git remote get-url origin)"
# Handles both https://github.com/USER/REPO.git and git@github.com:USER/REPO.git
user_repo="$(echo "$remote" | sed -E 's#(.*github.com[:/])([^/]+)/([^.]+)(\.git)?#\2/\3#')"
user="$(echo "$user_repo" | cut -d/ -f1)"
repo="$(echo "$user_repo" | cut -d/ -f2)"

echo
echo "Report URL:"
echo "  https://${user}.github.io/${repo}/${filename}"
