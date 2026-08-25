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

## 2026-08-25 — setup_wizard.py split into shell + mixins + widgets

setup_wizard.py was 1033 lines, over the 800 ceiling. Split into a 173-line
shell (navigation, `_finish_setup`) plus `wizard_widgets.py` (StepIndicator,
ModelDownloadThread, CameraPreview — underscore prefixes dropped so they are
importable), `wizard_content_steps.py` (welcome/API-keys/about-you/done), and
`wizard_device_steps.py` (camera/mic/model-download). The step builders moved
as mixins rather than standalone widgets because every page reads and writes
shared wizard state (`_collected`, `_stack`, `_next_btn`) — turning each page
into its own QWidget would have meant threading eight callbacks through
constructors for zero behavioral gain. Revisit if a page ever needs reuse
outside the wizard. Bonus fix in the move: the API-key "Get a key" link now
imports QUrl normally instead of via `__import__`.

## 2026-08-25 — Single-retry policy for dropped turns and STT download

Both engines now retry a failed turn exactly once, and only when the failure
produced zero output (no audio frame played, no transcript delta shown). A
drop after output started surfaces as an error instead — replaying would speak
and print a duplicate half-answer. On the OpenAI side the closed-connection
path raises a dedicated `ConnectionDropped` and the retry set is connection
errors only; Gemini opens a fresh session per turn anyway, so its retry
catches any pre-output exception. The Moonshine model fetch in `stt.py`
retries transient `OSError`s three times with linear backoff — Moonshine
caches completed files, so retries resume rather than restart the 245 MB
download. Rejected: resuming a mid-answer turn by asking the model to
"continue" — no reliable way to splice the audio, and the transcript would
not match what was spoken.

## 2026-08-25 — Async speech-model load at startup

`SpeechToText` construction (10–30 s on first run, seconds after) no longer
blocks the window: `AsyncSpeechToText` loads Moonshine on a daemon thread,
the capsule shows a new "Getting ready / Loading the speech model…" state
until it finishes, and `transcribe()` blocks until ready — so a question
asked during loading waits in its pipeline thread instead of failing or
needing an explicit queue. Rejected: an explicit queued-PTT mechanism for
the loading window — the blocking `transcribe()` gives the same behavior
with none of the queue's state.

## 2026-08-25 — Idle capture throttling

The window-capture loop (a full Quartz shot plus window enumeration per
frame) now runs at 5 fps only within 30 s of a wake (speech onset or PTT
key-down, piggybacked on the coordinator's warm-up hook) and drops to 1 fps
otherwise. Turn correctness is unaffected: `capture_text_context()` always
captures a fresh frame synchronously at question time. The visible cost is
the reading-source preview updating at 1 fps when you have not spoken for
30 s — pages are mostly static, and the first wake restores full rate before
the answer needs an image. Rejected: pausing capture entirely when idle —
the preview going frozen reads as a broken source, and 1 fps enumeration is
already cheap.

## 2026-08-25 — config split, Turn A: config_store.py owns the file

`klaus/config_store.py` now owns everything that touches config.toml as a
file: the data-dir paths, the default template, TOML parsing, raw
read/write, string escaping, and `set_top_level_value`. `config.py` (885 →
735 lines) keeps interpretation only — specs, coercion, RuntimeSettings,
and thin `save_*` validators that delegate. The old private names
(`_set_top_level_value`, `_DEFAULT_CONFIG_TEMPLATE`, …) stay as aliases so
nothing downstream moves. Turn B (making `_SettingSpec` generate the
dataclass fields, export map, and template section) is what gets the file
under 600.

## 2026-08-25 — config split, Turn B: spec table drives exports

The 33-line export-annotations block and the 34-entry `_RUNTIME_EXPORTS`
dict are gone: exports now generate from `_RUNTIME_SETTING_SPECS`
(upper-cased runtime field) plus a 4-entry `_EXTRA_EXPORTS` for the fields
built outside the spec table (API keys, user background, system prompt).
Kept explicit rather than generated: the `RuntimeSettings` dataclass —
`make_dataclass` would kill IDE navigation and typing for zero lines saved
that matter. Instead a consistency test holds the spec table, dataclass,
template, and exports together, which closes the drift bug class
(`ui_font_scale` really was missing from the template; fixed). config.py is
at 684 lines — above the 600 target, below the 800 ceiling; the remaining
bulk is the system prompt body (~120 lines), which moves out only if the
file grows again.

## 2026-08-25 — Closing ceiling audit

Every module is under the 800-line ceiling. Seven sit in the 600–760 flag
band; proposed splits, none urgent:

- `audio.py` (760): PushToTalkRecorder + VoiceActivatedRecorder + AudioPlayer
  share the file — the natural cut is VoiceActivatedRecorder (the VAD state
  machine) into its own module if barge-in work grows it further.
- `main.py` (745): down from 1176; what remains is wiring, the Qt signal
  bridge, and settings-dialog glue. Next cut would be a settings-apply
  service, worthwhile only if D10 (settings-in-UI scope) lands.
- `realtime.py` (703): grew with retry + warm-up; the event-loop body of
  `_ask_audio_once` could become a module-level function if it crosses 750.
- `settings_dialog.py` (694): splits per-tab if D10 adds VAD/hotkey tabs.
- `config.py` (684): remaining bulk is the system-prompt body; move to
  `prompts.py` on next growth.
- `theme_qss.py` (666) and `chat_widget.py` (636): stable; no split planned.

The final before/after latency table still needs Billy's 10 live turns per
engine (the TurnTimings aggregator logs p50/p95 every 10 turns); the code
side of the roadmap is complete apart from the D1–D10 owner decisions.

## 2026-08-25 — Barge-in self-trigger: wait for the speaker to drain

With barge-in on, Klaus's own answer started a new turn a bit after playback
finished. Cause: the output stream opens with `latency="high"` and is never
drained, so `ask_audio` returns (and teardown disarms the bleed-calibrated
barge-in gate) while the OS buffer is still playing the tail through the
speaker. The tail then fell to the ungated path — 450 ms settle plus a linear
cross-correlation echo match (0.75 threshold) that room reverb slips under.

Decision: estimate drain in `AudioOutput` (deadline = last write +
`stream.latency` + 150 ms margin, sound because `write()` blocks until buffer
space exists) and have the coordinator call `wait_for_drain()` before
`end_turn()`, so the gate stays armed until the tail is inaudible. A real
barge-in during the tail still works: turn_state is still speaking, and the
cancel path (`AudioOutput.stop()`) clears the deadline and unblocks the wait.
Applied to non-barge-in voice mode and replay too; PTT skips the wait.

Rejected: draining the stream (`stream.stop()`) at end of playback — races
the cross-thread cancel close and adds stopped-but-open state to the
persistent-stream design (see the 2026-08-25 latency-pass entry); lengthening
the hardcoded 450 ms/1200 ms windows — that extends exactly the path whose
echo matcher is the unreliable defense. Both windows stay as backstops.

Deferred owner decisions: gate VAD at `Vad(3)` instead of
`Vad(min(sensitivity, 2))` (docstring corrected to match the code); making
the 150 ms drain margin configurable. Revisit if Bluetooth sinks (buffering
PortAudio cannot see) still leak a tail past the estimate — the margin
constant is the knob. Also added a `barge_in` guard-stat counter so false
triggers are visible in logs.
