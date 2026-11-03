# How this brain is organised

## The folders
- **topics/** - notes that explain facts.  
- **patterns/** - notes that describe repeatable ways of working.  
- **references/** - notes that summarise external sources.  
- **projects/** - one note per project.  
- **sessions/** - notes that record a work session.  

Each top-level folder can contain any number of *domains* (sub-folders).  
Example domains: `web`, `infra`, `writing`.  
A note lives in `topics/web/why-the-build-cache-goes-stale.md` or similar.

## Naming
- File names are lower-case, hyphenated, and contain at least two words.  
- The first line under the title of every note is a plain sentence that says what the note is for, in the words you would search with.  
- Links use full paths inside double brackets, e.g. `[[topics/web/why-the-build-cache-goes-stale]]`.  

## The map
`MAP.md` is created automatically by the plugin.  
It lists every note together with the first-sentence description.  
The router reads this file to decide which notes match a prompt.  
Do not edit `MAP.md` by hand; run `brain.py map` to rebuild it.

## Rules
All rule files live in `rules/`.  
Each file follows the same Python shape and runs automatically on the events
`PreToolUse`, `PostToolUse`, or `Stop`.  
The full kit ships four rules (protect-env-files, session-note, no-invented-times, pattern-must-ship); `rules/README.md` explains them and how to add your own.

## Templates
`templates/` holds starter files for new notes:

- `session-note.md` - structure for a session record.  
- `topic-note.md` - structure for a fact note.  
- `pattern-note.md` - structure for a repeatable practice.  
- `project-note.md` - structure for a project overview.  

Create new notes from these templates to keep the vault consistent.

## Devlog
`devlog/` is written by the capture hook.  
Each line records a file that was changed during a session:

```
- 14:32 [my-project] src/cache.js
```

## Keeping it healthy
Run the following commands from a terminal:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/brain.py" map      # rebuild MAP.md
python3 "${CLAUDE_PLUGIN_ROOT}/bin/brain.py" check    # look for naming or content problems
python3 "${CLAUDE_PLUGIN_ROOT}/bin/brain.py" status   # show vault status and active rules
```

These commands keep the vault searchable and the rules working.
