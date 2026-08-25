---
name: obsidian
description: Create and maintain Obsidian Markdown notes from research conversations. Use when a user asks Klaus to capture, organize, connect, quote, summarize, find, or review material in an Obsidian vault, including note selection, wikilinks, properties, tags, callouts, and source references.
---

# Obsidian

Use the vault as a connected knowledge base, not a transcript dump.

## Choose the note

1. Use the exact target when the user names one.
2. Search the vault for the conversation topic when the user does not name one.
3. Reuse a matching note or the current note when it covers the same subject.
4. Otherwise infer a concise, specific `suggested_title` from the main topic.
5. Let the save tool create that note under `Klaus Notes/`.
6. Ask the user only when the topic or intended destination remains genuinely unclear.
7. Read an existing note first when its structure may affect the addition.

Treat every tool path as relative to the configured vault root.
Do not make the user invent a filename when the conversation provides a clear topic.

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

## Capture a chat

Use `configure_note_capture` when the user asks to save later turns automatically.

- Use `questions` for requests such as "save everything I ask."
- Use `conversation` when the user wants both their questions and Klaus's answers.
- Use `off` when the user asks to stop saving.
- Include `file_path` when the user names a target note.
- Otherwise pass a concise `suggested_title` inferred from the chat topic.
- Set `include_screenshots` to true when the user asks to capture screenshots too.
- Do not call `save_note` for each captured turn. Klaus appends captured turns after each completed response.
- A command that starts, changes, or stops capture is not itself captured.

## Save screenshots

Use `save_screenshot` when the user asks to save the current view or screenshot.

- Include `file_path` when the user names a target note.
- Otherwise pass a concise `suggested_title` inferred from the subject.
- Use a short factual caption when the user supplies useful context.
- Do not claim success when no screenshot is available.
- Klaus stores images under `Attachments/Klaus/` and embeds them in the note.

## End a chat

Use `save_chat_summary` when the user asks to wrap up or summarize the chat.

- Summarize the supplied chat transcript, including earlier stored exchanges.
- Include `suggested_title` when no suitable current note exists.
- Use concise `### Key ideas`, `### Decisions`, and `### Open questions` sections.
- Omit empty sections.
- Do not invent decisions, sources, or follow-up work.
- The tool stops automatic capture after it saves the summary.

## Finish

Report the exact vault-relative file path after a successful save.
State whether Klaus created the note or appended to it when the tool result provides that detail.
When capture changes, state what later turns Klaus will save.
Report the attachment path after saving a screenshot.
