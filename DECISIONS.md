# Decisions

Append-only log of choices, dead ends, and deviations. Newest last.

## 2026-08-23 — UI retheme: violet-biased dark palette, button hierarchy

Replaced the flat warm-gray palette with violet-biased neutrals that match the
existing `#aa9cf1` accent, and introduced a real button hierarchy: filled-accent
primary (`Save`, `New`, wizard next), quiet secondary (default `QPushButton`),
and ghost (card Copy/Replay, icon buttons). Settings tabs went from boxed
Windows-95 tabs to segmented pills; checkboxes, combo focus states, and the
hotkey keycap got styled. Rejected: reverting the font to bundled Inter —
commit 42e96a9 deliberately pinned Helvetica Neue on macOS the same day (with a
test), so Inter stays bundled-but-unused until that decision is revisited.
Revisit the palette if the accent changes; all values are tokens in
`klaus/ui/theme.py`.

Not done here: the chat thread still splits user/assistant messages to opposite
edges with dead space between them. Fixing it means touching
`klaus/ui/chat_widget.py`, which had uncommitted scroll/streaming work from a
parallel session at the time. Cap the thread at a centered ~860px column when
that work lands.

`theme.py` is at ~926 lines, over the 800-line module ceiling. Next change to
it should split the QSS string (e.g. `theme_qss.py`) from the tokens/helpers.
