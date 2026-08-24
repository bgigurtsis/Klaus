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

## 2026-08-24 — Voice dock redesigned as a single-line capsule; pill language app-wide

Chose the "Capsule" direction from five mocked proposals (hairline, capsule,
terminal status line, orb, composer-field). The dock is now one 52px pill:
state dot + state word + muted hint on the left, controls on the right; while
thinking/answering the capsule border tints toward the interrupt pink and the
right side collapses to a single small Stop pill. Deliberate removals: the
38px orb, the second text line, the "Switch to hands-free" hint sentence (now
a tooltip on the keycap and mode button), and the two-row compact reflow —
the capsule hides hint/stats/keycap progressively instead. Stop dropped the
alarm reds (#b91c1c) for LISTENING_COLOR pink: interrupting is a mic-hot
action, not an error. Buttons, combos, tabs, and chat example chips moved to
matching pill radii (half their height — Qt renders radius > height/2 badly,
so each radius is tuned per control, not a shared token). Rejected: the orb
variant (needs a custom-painted widget for its animation to earn the space)
and the terminal status line (no clickable Stop). Revisit if the pink border
tint reads as an error state in use.

Also done: the QSS finally split out of theme.py per the 2026-08-23 entry —
tokens/helpers stay in theme.py (~142 lines), main-window QSS in theme_qss.py
(~687), dialog/wizard QSS in theme_qss_dialogs.py (~181), all under the
800-line ceiling.

## 2026-08-24 — Development installs do not invoke ad-hoc codesign

Jamf Protect can flag the installer's `codesign --sign -` command through its
`AdhocCodeSigningWithCodesign` rule. The installer should now rely on the
ad-hoc signature that the Apple linker adds to the arm64 launcher. It should
not run the detected command. Developers can set `KLAUS_CODESIGN_IDENTITY`
when they have a certificate. The installer must reject `-` as an identity.
The build stamp should include this signing mode and a new format marker. The
marker should force one replacement of an app installed by the old path.

## 2026-08-24 — Sidebar and settings quieted to match the capsule

The sidebar's boxes were competing: filled accent + New, bold emphasized
combo, an always-visible empty preview card, shouting uppercase labels. Now:
sentence-case muted labels, badge as a colored word (inline style, states
Off/Waiting/Live in camera_widget._STATUS_STYLES), preview hidden until a
source is running, + New as an outline pill. The one filled-accent control
per surface rule: Save in settings, wizard next/primary — nothing in the
sidebar. Single-line QLineEdits are pills; QPlainTextEdit keeps a 12px
rectangle (a pill collapses visually on multi-line fields). Revisit hiding
the preview if users forget a source is selected while it's warming up.
