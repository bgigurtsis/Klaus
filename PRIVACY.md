# Privacy

Klaus runs on your Mac and sends live requests to the provider you select.

## Data sent to providers

Klaus may send recorded question audio and reading context to Gemini or OpenAI.
Reading context may include selected text, an active-window image, a Desk View image, or a Paper Pure screenshot.

Gemini Live can use Google Search grounding. GPT Live does not offer web search in Klaus.

Gemini and OpenAI handling follows each provider's terms, privacy policy, and account settings.

## Data stored on the Mac

Klaus stores settings in `~/.klaus/config.toml`.
Klaus stores its API key in Apple Keychain.
Klaus also stores the Paper Pure pairing password in Apple Keychain.
Klaus stores the tablet address, username, and certificate fingerprint in its settings.

Klaus stores session titles, transcripts, answers, and image hashes in `~/.klaus/klaus.db`.
Klaus does not store captured page images in that database.
Klaus keeps Paper Pure preview frames in memory and discards them after use.
Klaus may write notes into the Obsidian vault that you configure.
Logs may contain vault paths, device details, timing, and error messages.

## Your controls

You can disable camera access, selected-text access, or Obsidian integration.
You can remove the Gemini or OpenAI key in Settings.
You can delete `~/.klaus/klaus.db` to remove local session history.
You can inspect or delete `~/.klaus/config.toml` and `~/Library/Logs/Klaus/`.

Deleting local data does not delete data that a provider may retain.
Use the provider's controls for provider-side deletion requests.
