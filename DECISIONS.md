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

## 2026-08-24 — Text zoom via QSS post-processing, action-labeled mode button

Cmd+= / Cmd+- / Cmd+0 scale UI text (0.8–1.5x, ui_font_scale in config.toml).
Implementation choice: theme.application_stylesheet() regex-scales every
`font-size: Npx` in the assembled QSS rather than mutating the FONT_SIZE_*
tokens — theme_qss binds those names at import, so mutation would not reach
the stylesheet. Known residue: inline rich-text sizes (session list rows)
re-render only on the next data refresh, and fixed pixel chrome (capsule
height, keycap) deliberately does not scale. The dock mode button now names
the action ("Switch to push to talk"); the current mode lives in the tooltip.
Rejected: labeling the button with the current mode — that read as a state
badge, which is what confused in the first place.

## 2026-08-25 — Push-to-talk and audio-only startup defaults

New setups start in push-to-talk mode without a reading source. The main
reading-source menu keeps No reading source as a permanent option.

The mode button includes its shortcut and action in one label. Push-to-talk
idle state also names the mode and tells the user to hold `§` to talk.

## 2026-08-24 — Ad-hoc alerts persist; sign with a stable self-signed certificate

Removing the installer's `codesign --sign -` call (earlier today) did not stop
the Jamf Protect alerts: the arm64 linker still embeds an ad-hoc signature in
the launcher, and Jamf flagged a launch four minutes after a clean reinstall
by the new path. The rule matches the ad-hoc signature itself, not just the
codesign CLI. Fix: `scripts/create-signing-certificate.sh` creates a
self-signed "Klaus Code Signing" identity once (openssl + security import;
the trust step needs the user's password), and the installer now creates and
uses that identity when `KLAUS_CODESIGN_IDENTITY` is unset (`none` forces the
linker signature — the installer test uses this). A stable identity also
fixes the 2026-08-23 TCC-grant breakage, since the signing identity no longer
changes on every rebuild. Rejected: a Jamf-side exception (the CDHash changes
per rebuild, and the repo should not depend on MDM config). Revisit if macOS
tightens `security add-trusted-cert` further; the script prints Keychain
Access fallback steps when trust fails.

## 2026-08-24 — Launcher forks so the bundle stays the TCC responsible process

The "allowed but still prompted" Screen Recording bug had a second cause
beyond the unstable signature: launcher.c used execv, which replaced the
signed bundle binary with the venv Python before the app ever asked TCC for
access. This reverses the 2026-08-23 rejection of fork+waitpid — the stamp
mitigation did not hold in practice. The launcher now forks; the parent
stays alive as the responsible process, forwards SIGTERM/SIGINT/SIGHUP to
the child, and propagates its exit status (child _exit(127) = exec failed,
parent shows the alert). The installer also writes a signature-format file
into the bundle and, when the signing identity changes, runs `tccutil reset`
for ScreenCapture/Microphone/Camera on com.bgigurtsis.klaus — otherwise the
stale rows show ON in System Settings while matching nothing. The build
stamp now embeds the certificate hash (certificate-app-bundle-v2), so a
recreated certificate forces exactly one reinstall. Rejected: scripting
`security set-key-partition-list` to suppress the one-time codesign keychain
dialog — it puts the login password on a command line; "Always Allow" once
is fine. Revisit if the forked parent confuses the Dock or Force Quit
(contingency: LSUIElement in Info.plist).

## 2026-08-25 — Dead code removed: knowledge_profile, REALTIME_MODEL alias, dead QSS

Deleted the dormant knowledge-profile layer from `memory.py` (table DDL,
`update_knowledge`, `get_knowledge_summary`, `get_recent_exchanges_summary`)
— zero callers outside tests since the pipeline stopped injecting it. Existing
`knowledge_profile` tables in user databases are left in place: no migration,
the CREATE simply stops running, so old databases keep an unused table rather
than risking a destructive DROP. Also removed the `REALTIME_MODEL`
compatibility alias and single-provider `save_api_key` wrapper from
`config.py` (callers use `settings.live_model` and `set_api_key`), the never-
applied QSS selectors (`#conversation-*`, `#klaus-breadcrumb`,
`#klaus-brand-subtitle`, base `#chat-empty`), and the rule-less `wizard-dot`
object name. Revisit only if a knowledge profile feature returns — rebuild it
against the pipeline then, don't resurrect this code.

## 2026-08-25 — TurnState owns cross-thread turn flags; device switches refused mid-turn

KlausApp's five turn flags were mutated from four threads with no lock, and a
stop request could land on a stale cancel event because the event was rebound
inside the worker thread. `services/turn_state.py` now owns them behind one
lock: begin_turn creates the cancel event before the worker spawns, end_turn
consumes the barge-in seed and queued PTT recording atomically, and barge_in
rejects seeds when Klaus is not speaking. Memory's execute+commit write
sequences got a write lock (single-statement reads stay lock-free — sqlite's
serialized mode covers them). Device switches (camera and mic) are refused
with a dialog while a turn is processing, except the forced reMarkable
pairing refresh. Investigated and rejected: a pending-cancel flag for Gemini's
loop-startup window — `_cancelled()` already polls the event right after the
session opens, so an early cancel aborts the turn without new state; a
regression test now pins that.

## 2026-08-25 — main.py decomposed: hotkeys, SessionService, TurnCoordinator

main.py went from 1176 lines to 697 in three moves: `klaus/hotkeys.py` owns
the pynput gating and global listener (HotkeyListener with
set_keys/start/stop/restart); `services/session_service.py` owns session CRUD
and the activation sequence that was duplicated across switch/delete/startup
(now one `activate` path, and the vault-change notes rebind reuses
`sync_notes_bindings`); `services/turn_coordinator.py` owns everything that
starts, cancels, or tears down a voice turn (VAD callbacks, PTT, barge-in,
replay, stop, guard stats). Mutable collaborators (recorders, pipeline,
brain, input mode) reach the coordinator through getter lambdas because
KlausApp hot-swaps them on device switches and settings changes — chosen over
passing the app object (hidden coupling) and over re-wiring the coordinator
on every swap (churn). KlausApp keeps thin @_safe_slot delegates so Qt signal
connections and the safe-slot behavior stay in one place. Revisit the getter
pattern if a coordinator dependency stops being hot-swappable.

## 2026-08-25 — Latency pass: route-gated capture, persistent output stream

The pipeline now routes before capturing (routing is a local scoring pass on
both engines, so the old capture-concurrent-with-route thread was solving a
problem that no longer exists): the full-window text-context capture is
skipped on non-image routes, and the route thread is deleted. The audio
output stream stays open across playbacks — the accept-tone earcon and the
response no longer pay two device open/close cycles per turn — and cues are
skipped (not preempting) while a response plays, removing the
earcon-truncates-response hazard that was previously safe only by ordering.
Cancel (stop) still closes the stream for immediate silence; it reopens
lazily. Rejected: pre-encoding the API JPEG in the capture loop — each turn
already encodes at most once, and a 5 fps background encode trades constant
CPU for ~30 ms once per image turn. Also deliberately NOT changed yet:
`latency="high"` on the output stream and a receive-side prebuffer — both are
knobs to A/B against the TurnTimings baseline before touching (high latency
masks network jitter today; a prebuffer only pays for itself if latency
drops with it).
