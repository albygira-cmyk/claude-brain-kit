#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

# --remove-vault needs --yes: refuse before anything is touched, so a half-done uninstall never happens
if printf '%s\n' "$@" | grep -qx -- '--remove-vault' && ! printf '%s\n' "$@" | grep -qx -- '--yes'; then
  echo "Nothing was removed. --remove-vault deletes your notes: add --yes to confirm."
  exit 1
fi

# Uninstall the plugin from Claude Code (ignore errors if not present)
claude plugin uninstall bernard@bernard-brain-kit || true
claude plugin marketplace remove bernard-brain-kit || true

# Remove what the plugin owns (state, config, log); the vault only with --remove-vault --yes
python3 "$DIR/bin/brain.py" uninstall "$@"

# Final message
echo "Plugin removed. Your notes are untouched unless you passed --remove-vault --yes."
