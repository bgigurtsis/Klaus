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

## 2026-08-23 — Chat thread capped at a centered 860px column

The chat feed now lays messages out in a centered column
(`_COLUMN_MAX_WIDTH = 860` in `klaus/ui/chat_widget.py`) instead of letting
user and assistant cards hug opposite edges of a wide window. Qt gotcha worth
remembering: a widget between two `addStretch(1)` calls gets only its size
hint unless it carries a larger stretch factor itself — both the column and
the cards use `stretch=1000` so they fill up to their width caps before the
alignment stretches absorb the overflow. Known residue: `_sync_content_height`
pins each row's minimum height to a size hint measured mid-layout, which can
leave extra air inside assistant cards after resizes; left alone because that
mechanism is the recent scroll-clipping fix.

## 2026-08-23 — Ad-hoc re-signing silently breaks TCC grants

The "allowed but still banned" Screen Recording bug: `install-macos-app.sh`
ad-hoc signs Klaus.app, and an ad-hoc identity is a hash of the exact binary —
every reinstall creates a new identity, so the existing TCC grant row shows ON
in System Settings while no longer matching the running app. The installer now
writes a build-stamp (hash of launcher.c, Info.plist, icon, source root) and
skips the reinstall entirely when nothing changed, and warns about re-granting
when it does re-sign. Rejected for now: reworking launcher.c from execv to
fork+waitpid so the bundle stays the responsible process — more invasive, and
the stamp fix removes the common trigger. Revisit if grants still break, or
sign with a stable self-signed certificate instead.

## 2026-08-24 — Development installs do not invoke ad-hoc codesign

Jamf Protect can flag the installer's `codesign --sign -` command through its
`AdhocCodeSigningWithCodesign` rule. The installer should now rely on the
ad-hoc signature that the Apple linker adds to the arm64 launcher. It should
not run the detected command. Developers can set `KLAUS_CODESIGN_IDENTITY`
when they have a certificate. The installer must reject `-` as an identity.
The build stamp should include this signing mode and a new format marker. The
marker should force one replacement of an app installed by the old path.
