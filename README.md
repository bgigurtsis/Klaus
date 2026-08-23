<p align="center">
  <img src="https://raw.githubusercontent.com/bgigurtsis/Klaus/main/klaus/ui/icon.png" width="320" alt="Klaus, a scholarly lobster reading a research paper">
</p>

<h1 align="center">Klaus</h1>

<p align="center">
  <strong>A voice assistant for reading papers and PDFs on macOS.</strong>
</p>

<p align="center">
  <a href="https://github.com/bgigurtsis/Klaus/actions/workflows/ci.yml"><img src="https://github.com/bgigurtsis/Klaus/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://pypi.org/project/klaus-assistant/"><img src="https://img.shields.io/pypi/v/klaus-assistant" alt="PyPI version"></a>
  <img src="https://img.shields.io/badge/macOS-12%2B-111111" alt="macOS 12 or later">
  <a href="https://github.com/bgigurtsis/Klaus/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-6f55a5" alt="MIT License"></a>
</p>

Klaus can answer spoken questions about the page in front of you. It may read papers through Apple Desk View. It can also use selected text or an image from the active PDF window. Klaus keeps answers short, supports follow-up questions, and can save notes to Obsidian.

## Quick setup

You need macOS 12 or later, a microphone, and an [OpenAI API key](https://platform.openai.com/api-keys).

```sh
brew tap bgigurtsis/klaus
brew install klaus
klaus
```

The first-launch guide sets up your API keys, reading source, microphone, local speech model, and optional Obsidian vault.

Klaus may ask for these macOS permissions:

- **Microphone** for spoken questions.
- **Screen Recording** for Desk View and PDF window images.
- **Accessibility** for global hotkeys and selected PDF text.

You can deny Accessibility and use the buttons in Klaus. PDF questions may then use a window image instead of selected text.

## What Klaus can do

- Read papers through Apple Desk View.
- Read selected text or capture the active PDF window.
- Answer through one live GPT Realtime voice conversation.
- Stop an answer when you start speaking.
- Search the web through Tavily when current information matters.
- Search, read, and append notes inside a configured Obsidian vault.
- Keep local reading sessions and conversation history.

## Use Klaus

### Read a paper

1. Open Apple Desk View.
2. Choose **Desk View: paper** in Klaus.
3. Frame the page and ask a question.

### Read a PDF

1. Open the PDF in Preview, a browser, or another macOS app.
2. Choose **Active window: PDF** in Klaus.
3. Keep the PDF window in front.
4. Select text when you want Klaus to use an exact passage.

### Control the conversation

Klaus starts in hands-free mode. Hold `§` for push-to-talk. Press `Shift+§` to switch modes. Start speaking over an answer to interrupt it.

### Save an Obsidian note

Choose a vault during setup or in **Settings**. Then say where Klaus should save the note:

> Save this to Research/Agent Notes.md.

Klaus accepts only paths inside that vault. It appends to existing notes instead of replacing them.

## API keys and data

| Provider | Required | Used for |
|---|---:|---|
| [OpenAI](https://platform.openai.com/api-keys) | Yes | Live voice, page reasoning, and spoken answers |
| [Tavily](https://app.tavily.com/home) | No | Web search |
| [Anthropic](https://console.anthropic.com/settings/keys) | No | Legacy Claude voice engine |

Klaus stores API keys in Apple Keychain. It stores settings and conversation history under `~/.klaus/`. It does not store captured page images in its database.

Provider use may incur charges. Read the [privacy notes](https://github.com/bgigurtsis/Klaus/blob/main/PRIVACY.md) before you connect accounts or private notes.

## Settings

Open **Settings** in Klaus for normal changes. Advanced settings live in `~/.klaus/config.toml`.

| Setting | Default | Purpose |
|---|---:|---|
| `voice_engine` | `realtime` | Use GPT Realtime or the `legacy` Claude and OpenAI TTS path |
| `camera_index` | `0` | Use Desk View with `-2`, active PDF with `-3`, or audio only with `-1` |
| `input_mode` | `voice_activation` | Use hands-free or push-to-talk input |
| `stt_moonshine_model` | `medium` | Choose the local speech model size |
| `log_level` | `INFO` | Set log detail |

## Build from source

Install Python 3.11 through 3.13 and PortAudio first.

```sh
brew install python@3.13 portaudio
git clone https://github.com/bgigurtsis/Klaus.git
cd Klaus
python3.13 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/klaus
```

To add the development build to Finder and Spotlight:

```sh
./scripts/install-macos-app.sh
open "$HOME/Applications/Klaus.app"
```

The app points to this checkout. Rerun the installer after you move the repository.

## Project

- Read the [contribution guide](https://github.com/bgigurtsis/Klaus/blob/main/CONTRIBUTING.md) before you open a pull request.
- Follow the [security policy](https://github.com/bgigurtsis/Klaus/blob/main/SECURITY.md) to report suspected vulnerabilities.
- Klaus uses the [MIT License](https://github.com/bgigurtsis/Klaus/blob/main/LICENSE).
- The bundled Inter fonts retain the [SIL Open Font License](https://github.com/bgigurtsis/Klaus/blob/main/klaus/ui/fonts/LICENSE.txt).

Klaus is alpha software. Features and stored data formats may change between releases.
