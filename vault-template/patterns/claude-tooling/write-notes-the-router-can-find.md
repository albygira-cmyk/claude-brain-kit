---
type: pattern
tags: [bernard, notes, writing]
last_updated: 2026-10-26
---

# Write notes the router can find

How to write a note so the BERNARD router finds it later: a specific two-plus-word filename, a plain first sentence with the words you would search for, and full-path wikilinks.

## When to use it

Create a note when you want the brain to retrieve it for future prompts.  
Use a clear, searchable filename and a first sentence that contains the key terms you expect to type later.

## Implementation

**Filename**  
- Bad: `notes.md` or `proxy.md` - too generic, the router cannot match it.  
- Good: `build-cache-goes-stale-after-rename.md` - two-plus-word, hyphenated, descriptive.

**First sentence**  
- Bad: `# Overview` or `- important point` - not a plain sentence, the router skips it.  
- Good: `The cache becomes stale after a file is renamed and the build script does not notice the change.` - one plain sentence with searchable words.

**Wikilinks**  
- Bad: `[[some-note]]` - missing full path, the router cannot locate it reliably.  
- Good: `[[topics/web/some-note]]` - full path from the vault root, the router can follow it.

Write the note with frontmatter, a title, then the first sentence on its own line, followed by any content you need. The map shows that sentence, and the keyword ranker scores it; the body is only reached by the second ranker (word frequency), so a vague first sentence hides a good note.

## Used in

- The map builder puts the first sentence next to every note in `MAP.md`.
- The router scores the note name and that sentence for every prompt, then word frequency over the body.
- The `check` command (`brain.py check`) lists notes with no first sentence or a bad filename.
