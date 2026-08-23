---
name: obsidian
description: Create and maintain Obsidian Markdown notes from research conversations. Use when a user asks Klaus to capture, organize, connect, quote, summarize, find, or review material in an Obsidian vault, including note selection, wikilinks, properties, tags, callouts, and source references.
---

# Obsidian

Use the vault as a connected knowledge base, not a transcript dump.

## Choose the note

1. Ask for a target file when the user does not name one.
2. Search the vault before creating a note with the same topic.
3. Reuse the current note when the request continues the same subject.
4. Set the notes file before saving content.
5. Read the note first when its structure or prior content may affect the addition.

Treat every tool path as relative to the configured vault root.

## Write useful Markdown

- Match the note's existing heading, list, and property style.
- Preserve the user's wording when they dictate exact text.
- Use `[[wikilinks]]` only for clear concepts or notes that may exist.
- Use `[[Note title|display text]]` when sentence grammar needs different text.
- Add tags only when the note already uses them or the user requests them.
- Use blockquotes for exact quotations.
- Add page, section, figure, or URL references when the source provides them.
- Mark uncertain paraphrases as uncertain.
- Prefer one useful heading and compact bullets over repeated headings.
- Do not duplicate content that the note already contains.

## Create a note

For an empty note, start with a clear title or useful properties when the user requests them.

Use this default shape when no local pattern exists:

```markdown
# Topic

## Notes

- Main point with a [[Related concept]] and source reference.

## Questions

- Open question to revisit.
```

Do not invent authors, dates, tags, links, quotes, or source locations.

## Finish

Report the exact vault-relative file path after a successful save.
State whether Klaus created the note or appended to it when the tool result provides that detail.
