# Privacy

Klaus runs on your Mac and sends enabled Realtime requests to OpenAI.

## Data sent to providers

Klaus may send recorded question audio and reading context to OpenAI.
Reading context may include text selected in any app, an active-window image, or a camera image.

OpenAI handling follows its terms, privacy policy, and account settings.

## Data stored on the Mac

Klaus stores settings in `~/.klaus/config.toml`.
Klaus stores its API key in Apple Keychain.

Klaus stores session titles, transcripts, answers, and image hashes in `~/.klaus/klaus.db`.
Klaus does not store captured page images in that database.
Klaus may write notes into the Obsidian vault that you configure.
Logs may contain vault paths, device details, timing, and error messages.

## Your controls

You can disable camera access, selected-text access, or Obsidian integration.
You can remove the OpenAI key in Settings.
You can delete `~/.klaus/klaus.db` to remove local session history.
You can inspect or delete `~/.klaus/config.toml` and `~/Library/Logs/Klaus/`.

Deleting local data does not delete data that a provider may retain.
Use the provider's controls for provider-side deletion requests.
