#!/usr/bin/env bash
# install.sh: register this folder as a Claude Code plugin marketplace, install the plugin, set up the vault.
# Run it from the folder you unzipped into (a permanent one: the plugin runs from here).
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# Python 3.8+ check
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' 2>/dev/null \
  || { echo "Python 3.8 or newer is needed. On a Mac: xcode-select --install, or install Python from python.org."; exit 1; }

# Claude command check
command -v claude >/dev/null 2>&1 \
  || { echo "Claude Code is not installed or not on PATH. Install it first: https://claude.com/claude-code"; exit 1; }

# Do not run from Downloads
case "$DIR" in
  "$HOME"/Downloads* )
    echo "Move this folder somewhere permanent first (for example ~/bernard-brain-kit). The plugin runs from this folder, and Downloads gets cleaned out."
    exit 1
    ;;
esac

# Add this folder as a marketplace. If an older copy is registered under the same name (a previous unzip,
# another folder), replace it with this one so the plugin runs from here.
if ! claude plugin marketplace add "$DIR" >/dev/null 2>&1; then
  echo "A marketplace named bernard-brain-kit is already registered: pointing it at this folder."
  claude plugin uninstall bernard@bernard-brain-kit >/dev/null 2>&1 || true
  claude plugin marketplace remove bernard-brain-kit >/dev/null 2>&1 || true
  claude plugin marketplace add "$DIR"
fi

# Install (or re-install) the plugin for this user
if ! claude plugin install bernard@bernard-brain-kit --scope user; then
  claude plugin uninstall bernard@bernard-brain-kit >/dev/null 2>&1 || true
  claude plugin install bernard@bernard-brain-kit --scope user
fi

# Initialise the brain with any arguments passed to install.sh (for example --vault ~/notes)
python3 "$DIR/bin/brain.py" init "$@"

echo "Installed. Open a new Claude Code session: its first lines of context will say \"BERNARD brain: on\"."
