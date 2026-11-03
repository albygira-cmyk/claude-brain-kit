---
name: find
description: Use when the user asks "what do you know about X", "check your notes", "did we solve this before", or when the BERNARD ROUTE packet said NO_RELEVANT_MEMORY and the user says it was saved. Searches the vault by hand and answers with note paths, never an invented memory.
---

# Find it in the brain

The vault path is in the session's first lines (`Vault: ...`).

1. Search the map first; it has one line per note with its description:
   ```bash
   grep -i "word1\|word2" "<vault>/MAP.md"
   ```

2. Then search the note bodies (names and descriptions miss things):
   ```bash
   grep -ril "word1\|word2" "<vault>/topics" "<vault>/patterns" "<vault>/references" "<vault>/projects" "<vault>/sessions"
   ```
   Try a synonym or a shorter stem if both come back empty.

3. Read at most two of the matching notes in full (prefer topics/patterns over sessions; prefer the newest).

4. Answer with what the notes say and their paths, one per line. Quote the note for anything specific (a
   number, a decision, a command). Do not claim a note was read unless its path is in your answer.

5. If nothing matches, say so plainly: "There is no note about that in the vault." Never invent a memory.
   If the user insists it was saved, ask where they saw it saved, and check `<vault>/sessions/` by date.
