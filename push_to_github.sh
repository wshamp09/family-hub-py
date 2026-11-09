#!/bin/bash
# Push this folder to the app's GitHub repo, which Streamlit Community Cloud deploys from.
# Works in a freshly unzipped folder (no git history yet) and in a folder that's already set up.
#
#   bash push_to_github.sh                      # commit message: "Update <date time>"
#   bash push_to_github.sh "What changed"       # your own commit message
#
# Set REPO below if your repo has a different address.
REPO="${FH_REPO:-https://github.com/wshamp09/family-hub-py.git}"
BRANCH="main"

set -e
cd "$(dirname "$0")"
MSG="${1:-Update $(date '+%Y-%m-%d %H:%M')}"
step() { echo; echo "==> $1"; }

step "1/6 Checking the folder"
if [ ! -f streamlit_app.py ]; then
  echo "STOP: streamlit_app.py isn't here. Put this script in the app folder and run it there."; exit 1
fi
if [ ! -f .gitignore ] || ! grep -q "secrets.toml" .gitignore; then
  echo "STOP: .gitignore is missing or doesn't list secrets.toml, so your secrets could be uploaded."; exit 1
fi
echo "OK: $(pwd)"

step "2/6 Setting up git"
if [ ! -d .git ]; then
  git init -q
  echo "Started git in this folder."
else
  echo "Git already set up here."
fi
git checkout -q -B "$BRANCH" 2>/dev/null || git branch -M "$BRANCH"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO"
else
  git remote add origin "$REPO"
fi
echo "GitHub repo: $REPO"

step "3/6 Getting what's already on GitHub"
if git fetch -q origin 2>/dev/null; then
  if git rev-parse -q --verify "origin/$BRANCH" >/dev/null; then
    # Line this folder's history up with GitHub's, keeping every file in the folder exactly as it is.
    git reset -q --soft "origin/$BRANCH"
    echo "Lined up with GitHub (your files are unchanged)."
  else
    echo "The repo is empty; this will be its first upload."
  fi
else
  echo "STOP: couldn't reach $REPO"
  echo "Check the repo exists on github.com (private is fine) and the address above is right."; exit 1
fi

step "4/6 Collecting changes"
git add -A
BAD=$(git ls-files | grep -E "(^|/)secrets\.toml$|(^|/)\.venv/" || true)
if [ -n "$BAD" ]; then
  git reset -q
  echo "STOP: these must never be uploaded, so nothing was committed:"; echo "$BAD"; exit 1
fi
echo "Secrets and .venv are left out."
git status --short | sed 's/^/   /' | head -40
CHANGED=$(git status --short | wc -l | tr -d ' ')
echo "$CHANGED file(s) changed."

step "5/6 Saving a commit"
if git diff --cached --quiet; then
  echo "Nothing new to commit."
else
  git commit -q -m "$MSG"
  echo "Committed: $MSG"
fi

step "6/6 Uploading to GitHub"
git push -u origin "$BRANCH"
echo
echo "Done. Streamlit Community Cloud redeploys the app in a minute or two."
