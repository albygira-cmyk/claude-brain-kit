---
type: pattern
tags: [rules, hooks, reliability]
last_updated: 2026-10-26
---

# A prompt rule is a preference, a hook is a guarantee

If something must happen every time, it cannot live only in a prompt or a CLAUDE.md line; it has to run as a hook that blocks.

## Why
A model weighs a written rule against everything else in the turn: the task, the user's tone, the last file it read. The result is whatever survived the weighing, and on a long turn the rule often does not. A hook does not weigh anything: it runs, and when the rule is broken it blocks, every time.

## When to use it
- When a rule is written only in a prompt, the only evidence it was followed is the agent's own report. That is the tell: if you cannot check it from outside, it is a preference.
- Use a hook when the rule must be enforced regardless of what the model says.  
- Typical cases: never edit `.env` files, always write a session note before finishing, require a pattern note to be shipped before the next turn.  
- Choose **once** (block only the first violation in a session) for rules that are costly to repeat, such as prompting the user to write a session note.  
- Choose **every time** for safety-critical rules, like protecting environment files.

## Implementation
1. Create a Python file in `vault/rules/` (e.g., `protect-env-files.py`).  
2. Fill the required constants:  
   ```python
   """Never edit .env files."""
   EVENT = "PreToolUse"
   TOOLS = "Write|Edit|MultiEdit|NotebookEdit|Bash"
   ONCE = False
   ```  
3. Write a `check(payload, ctx)` function that returns a plain-language message when the rule is broken, otherwise `None`.  
4. The rule is automatically loaded by `hooks/rules.py`.  
5. Test the rule by breaking it on purpose, then by keeping it:  
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/brain.py" rule test protect-env-files --tool Write --file .env       # BLOCKS, exit 2
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/brain.py" rule test protect-env-files --tool Write --file notes.md   # PASSES, exit 0
   ```  
   A guard you never saw fire is a guard you do not know works.  
6. If the rule should fire only once per session, set `ONCE = True`. The runner will remember the first block and let later violations pass.

## Used in
- `rules/protect-env-files.py` - blocks any write or edit of a `.env` file on every occurrence.  
- `rules/session-note.py` - fires once at the end of a session to remind the user to write a session note.  
- `rules/no-invented-times.py` - fires once at the end of a session to catch invented timestamps.  
- `rules/pattern-must-ship.py` - fires once at the end of a session to ensure a written pattern is wired into a rule or setting.
