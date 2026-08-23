# Privacy

Klaus runs on your Mac, but some features may send data to configured providers.

## Data sent to providers

The default Realtime engine may send recorded question audio and reading context to OpenAI.
Reading context may include text selected in any app, an active-window image, or a camera image.

The legacy engine may send transcripts, reading context, conversation context, and tool results to Anthropic.
It may send generated answer text to OpenAI for speech output.

Klaus may send search queries to Tavily when web search is enabled.
Provider handling may follow each provider's terms, privacy policy, and account settings.

## Data stored on the Mac

Klaus stores settings in `~/.klaus/config.toml`.
Klaus stores API keys in Apple Keychain when Keychain is available.
Klaus may keep legacy plaintext keys in `config.toml` when Keychain is unavailable.

Klaus stores session titles, transcripts, answers, search results, and image hashes in `~/.klaus/klaus.db`.
Klaus does not store captured page images in that database.
Klaus may write notes into the Obsidian vault that you configure.
Logs may contain search queries, vault paths, device details, timing, and error messages.

## Your controls

You can disable camera access, selected-text access, web search, or Obsidian integration.
You can remove a provider key in Settings.
You can delete `~/.klaus/klaus.db` to remove local session history.
You can inspect or delete `~/.klaus/config.toml` and `~/Library/Logs/Klaus/`.

Deleting local data does not delete data that a provider may retain.
Use the provider's controls for provider-side deletion requests.
