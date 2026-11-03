---
name: setup
description: Use when the user says "set up the brain", "turn on memory", "install bernard", "my Claude forgets everything", "it ignores my rules", or when the session began with "BERNARD brain: not set up yet". Creates the vault and turns memory on.
---

# Set up the brain

1. Create the vault and the map:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/brain.py" init
   ```
   If `${CLAUDE_PLUGIN_ROOT}` is not expanded in your shell, use the CLI path printed in the session's first lines
   (`CLI: python3 "<plugin folder>/bin/brain.py"`). To keep notes somewhere else: `init --vault ~/some/folder`.

2. Confirm it worked:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/brain.py" status
   ```

3. Tell the user, in five short lines, what happens from now on:
   - Every prompt arrives with a "BERNARD ROUTE" packet: the notes from the vault that match it.
   - Every file Claude changes is recorded in the vault's devlog and an in-progress session note (full kit).
   - Before Claude finishes a turn that changed files, a rule asks for a real session note (full kit).
   - The rules that are on (from `status`); each blocks a specific thing and says what to do instead.
   - Where the notes live (the vault path from `status`), and that they are plain Markdown files.

4. Offer to write the first project note for the current folder. If the user says yes:
   - Read what is there: `README*`, `package.json`, `pyproject.toml`, or the folder listing.
   - Write `<vault>/projects/<folder-name-slug>.md` from `<vault>/templates/project-note.md`: a plain first
     sentence saying what the project is for, then Goal and Current state.
   - Rebuild the map: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/brain.py" map`

5. Say that a new Claude Code session will start with `BERNARD brain: on`, and that the packet appears from the
   first real prompt in it.
