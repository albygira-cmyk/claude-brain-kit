---
type: topic
tags: [bernard, memory, retrieval]
last_updated: 2026-10-26
---

# How this brain finds notes

How the BERNARD router picks which notes Claude sees for a prompt, and why a note's first sentence decides whether it is ever found.

## Packet and memory_status values

The router builds a **BERNARD ROUTE** packet for each prompt.  
`memory_status` can be:

* **MATCHES_FOUND** - notes were selected and placed in the packet.  
* **NO_RELEVANT_MEMORY** - the router ran but no note scored above the threshold.  
* **EMPTY_VAULT** - the vault has no notes at all.  
* **RETRIEVAL FAILED** - an error occurred while ranking.

The packet contains the note paths, a short description, and the note text (truncated if needed).

## Two rankers in plain words

* **Keyword ranker** - compares the words of the prompt to each line in `MAP.md`.  
  The note name (the part after the last slash) counts most, the description counts less.

* **BM25 ranker** - looks at the full bodies of notes.  
  Words that appear often in a note but rarely across all notes get higher weight.

The router ranks the notes with each ranker separately, then fuses the two ordered lists with reciprocal-rank fusion: a note near the top of either list comes out near the top. Up to 5 notes (at most 2 project notes) and 2 skills are inlined; the score shown next to a note is its keyword score.

## 8,600-character cap and why

The injected context for a prompt may not exceed 8,600 characters.  
If the combined text of the packet is longer, the router truncates note bodies and adds a "TRUNCATED" notice.  
Claude Code turns any longer injection into a file-path reference, which would break the experience.

## Required reads

If a note does not fit within the packet, its path is listed under **required_reads**.  
Claude must open those notes before deciding how to act.

## Automatic map rebuild

Whenever a note is added, edited, or removed, the router checks the map timestamp.  
If any note is newer than `MAP.md`, the map is rebuilt automatically before the next prompt.

## What makes a note findable

* The note lives in one of the top-level folders (`topics`, `patterns`, `references`, `projects`, `sessions`).  
* Its filename is lower-case, hyphenated, and contains at least two words.  
* The first line after any frontmatter is a plain sentence describing the note.  
* That sentence appears in `MAP.md` as the note's description.  
* The description contains words that the user might type when asking a question.  

A note that misses these is still indexed, but it is much harder to find: with no first sentence the map shows nothing for it, and the keyword ranker only has the filename to go on.
