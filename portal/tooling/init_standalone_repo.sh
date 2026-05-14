#!/usr/bin/env bash
# One-time: make THIS folder (Fabio_bot) the Git repository root with full history
# from the parent "Cursor Projects" monorepo, then stop the parent from tracking
# Fabio_bot/ (adds Fabio_bot/ to parent .gitignore).
#
# Run from Terminal.app / iTerm (outside Cursor) if you see
#   .git/hooks/: Operation not permitted
# — some environments block hook installation until you use a normal shell.
#
# Usage (from Fabio_bot root):
#   bash portal/tooling/init_standalone_repo.sh

set -euo pipefail

FABIO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MONO_ROOT="$(cd "$FABIO_ROOT/.." && pwd)"

if [[ "$(basename "$FABIO_ROOT")" != "Fabio_bot" ]]; then
  echo "Expected Fabio_bot root; got: $FABIO_ROOT" >&2
  exit 1
fi

if [[ ! -d "$MONO_ROOT/.git" ]]; then
  echo "Parent monorepo .git not found at: $MONO_ROOT/.git" >&2
  exit 1
fi

# Remove broken partial .git (e.g. failed init left an empty hooks dir)
if [[ -d "$FABIO_ROOT/.git" ]] && [[ ! -f "$FABIO_ROOT/.git/HEAD" ]]; then
  echo "==> Removing incomplete Fabio_bot/.git"
  rm -rf "$FABIO_ROOT/.git"
fi

if [[ -f "$FABIO_ROOT/.git/HEAD" ]]; then
  echo "Fabio_bot already looks like a Git repo (.git/HEAD exists)." >&2
  echo "To re-run from scratch: rm -rf \"$FABIO_ROOT/.git\"" >&2
  exit 1
fi

echo "==> Refresh subtree branch in monorepo (orbit-bot-export-main)"
git -C "$MONO_ROOT" fetch origin 2>/dev/null || true
git -C "$MONO_ROOT" branch -D orbit-bot-export-main 2>/dev/null || true
git -C "$MONO_ROOT" subtree split --prefix=Fabio_bot -b orbit-bot-export-main

echo "==> git init in Fabio_bot (hooksPath=/dev/null avoids sample hooks in some setups)"
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=core.hooksPath
export GIT_CONFIG_VALUE_0=/dev/null
git -C "$FABIO_ROOT" init -b main
unset GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0

git -C "$FABIO_ROOT" remote add monorepo "$MONO_ROOT"
git -C "$FABIO_ROOT" fetch monorepo orbit-bot-export-main:main
git -C "$FABIO_ROOT" checkout -f main
git -C "$FABIO_ROOT" remote remove monorepo
git -C "$FABIO_ROOT" config core.hooksPath /dev/null

echo "==> Set origin to ORBit-BOT (edit script if you use SSH)"
git -C "$FABIO_ROOT" remote add origin "https://github.com/connectwithclayton-cpu/ORBit-BOT.git" 2>/dev/null || \
  git -C "$FABIO_ROOT" remote set-url origin "https://github.com/connectwithclayton-cpu/ORBit-BOT.git"

echo "==> Stop parent repo from tracking Fabio_bot/"
if git -C "$MONO_ROOT" ls-files --error-unmatch Fabio_bot/README.md >/dev/null 2>&1; then
  git -C "$MONO_ROOT" rm -r --cached Fabio_bot
fi
if ! grep -qx 'Fabio_bot/' "$MONO_ROOT/.gitignore" 2>/dev/null; then
  printf '\n# Standalone repo — entire tree is its own Git project\nFabio_bot/\n' >> "$MONO_ROOT/.gitignore"
fi

echo ""
echo "Done. Next steps (you run these outside this script):"
echo "  1) cd \"$MONO_ROOT\" && git status && git commit -m \"Stop tracking Fabio_bot (standalone repo)\""
echo "  2) cd \"$FABIO_ROOT\" && git push -u origin main"
echo ""
echo "Then open ONLY the Fabio_bot folder in Cursor / GitHub Desktop as the repository root."
