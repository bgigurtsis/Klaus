# Klaus functional audit, 11 September 2026

This audit covers the local app, its main flows, and both provider implementations. The tests can reproduce two paths that let speaker output become input. The fixes address those paths, but they cannot establish echo-free behavior on every microphone and speaker combination.

| Area | Failure before this change | Fix and evidence |
| --- | --- | --- |
| Buffered speech | A provider could return after waiting ten seconds even while queued audio continued playing. | Both providers now wait for the playback worker. GPT answer and replay tests hold playback for 10.1 seconds. |
| Echo gate | A quiet lead-in followed by louder echo could dilute waveform matching and trigger an interruption. | The gate compares the voiced portion while retaining the lead-in for real interruptions. A synthetic gain-change test covers this case. |
| Speaker timing | A microphone could hear a block before the output observer received it. Long device latency could also outlast the drain guard. | The observer receives each block before its write. The drain guard honors valid reported latency below ten seconds. |
| Stop and audio errors | A cancelled worker could remain blocked on an empty queue. Device errors could disappear inside its thread. | Queue waits now check cancellation. Playback errors reach the UI. Stop aborts buffered output. Failed stream starts release the device. |
| Echo transcripts | Shared vocabulary could cause a real follow-up to match the previous answer. Discarded input could extend the echo window. | Matching now requires a consecutive phrase. Discarding input no longer refreshes playback time. Replay supplies its text to the guard. |
| Replay | Replay could overlap another turn, replace its cancellation event, or fail to hand off a queued question. | Replay now claims the turn, passes cancellation to both providers, and hands off queued push-to-talk input. GPT replay can time out a missing cancellation acknowledgment. |
| Microphone selection | Push-to-talk could ignore the selected microphone. Failed starts could leave it marked as recording. | Both recording modes use the selected device. Startup failures reset recording state and show an error. Push-to-talk stops leftover playback before recording. Replay cannot start during a push-to-talk recording. |
| Chat streaming | After a provider error, the next answer could append to the previous partial answer. | The error handler detaches the partial card before another turn starts. |
| Setup | Back navigation could reset the reading source. Choosing audio-only could leave an older source configured. | Setup preserves the selection and saves the audio-only choice. |
| Settings | A rejected device choice could still persist. Voice capture could overlap client reconfiguration. | The app saves the effective device. Settings pauses capture and restores it after applying changes. |
| Sessions | Switching chats during an answer could rebind its notes. Deleting another chat could change the active chat. | Active turns block chat changes. Deleting a different chat preserves the active one. |
| Persistence | A late cancellation could still save a completed exchange. Missing sessions could receive orphan exchanges. | The pipeline checks cancellation after provider return. Storage requires an existing session. |
| Obsidian capture | Stopping capture could leave screenshot capture enabled. | Stopping capture clears that option. The pipeline also ignores it on older sessions whose capture mode is off. |
| Gemini tools | Cancellation could allow later calls in a tool batch to continue. | Gemini checks cancellation before and after each local tool call. |

The baseline passed 320 tests. Nine added regression cases fail against the original source at `22e100f`. These failures can demonstrate gaps in that baseline. The updated suite passes 353 tests with isolated app data and local mock servers. Syntax compilation, whitespace checks, and dependency checks also pass.

The full suite covers voice detection, speculative transcription, routing, provider streaming, replay, cancellation, notes, sessions, setup, settings, permissions, hotkeys, chat layout, image viewing, reading sources, tablet pairing, and installation. Mocked provider and tablet checks can verify application behavior without proving a live service works.

The local environment carried package metadata for 0.3.3. Refreshing the editable installation to 0.4.0 cleared its dependency errors. The macOS installer reports the app current and preserves its existing signing identity. Its source-root points to this checkout. A fresh launch restores the saved chat, shows the active-window preview, opens microphone settings without an unavailable-device message, and returns to push-to-talk after Settings closes.

The remaining limits require separate verification:

- Real speaker-to-microphone echo still needs an acoustic test, including Bluetooth devices and changing output volume. The waveform and transcript guards remain heuristics.
- Paid OpenAI and Gemini calls, live Google Search, and provider authentication were not exercised. The audit therefore cannot certify current provider availability.
- Physical Desk View and reMarkable capture need the corresponding hardware. Their automated tests use fixtures and local mock servers.
- Stop can prevent later Gemini tool calls, but an in-flight local note operation must return before the turn finishes. This change does not attempt to interrupt a file write midway.
