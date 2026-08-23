<p align="center">
  <img src="https://raw.githubusercontent.com/bgigurtsis/Klaus/main/klaus/ui/icon.png" width="320" alt="Klaus, a scholarly lobster reading a research paper">
</p>

<h1 align="center">Klaus</h1>

<p align="center">
  <strong>Voice-powered research assistant for physical and digital media.</strong>
</p>

<p align="center">
  <a href="https://github.com/bgigurtsis/Klaus/actions/workflows/ci.yml"><img src="https://github.com/bgigurtsis/Klaus/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://pypi.org/project/klaus-assistant/"><img src="https://img.shields.io/pypi/v/klaus-assistant" alt="PyPI version"></a>
  <img src="https://img.shields.io/badge/macOS-12%2B-111111" alt="macOS 12 or later">
  <a href="https://github.com/bgigurtsis/Klaus/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-6f55a5" alt="MIT License"></a>
</p>

Klaus can answer spoken questions about a physical page or anything in your active window. It can read papers through Apple Desk View. It can also use selected text or an image from any macOS app. Klaus keeps answers short, supports follow-up questions, and can save notes to Obsidian. GPT Realtime powers the live conversation.

## Install Klaus

You need macOS 12 or later, a microphone, and an [OpenAI API key](https://platform.openai.com/api-keys).

### Homebrew

```sh
brew tap bgigurtsis/klaus
brew install klaus
klaus
```

### PyPI

Klaus needs Python 3.11 through 3.13 and PortAudio. Create a virtual environment before you install it from PyPI.

```sh
brew install python@3.13 portaudio
python3.13 -m venv .venv-klaus
.venv-klaus/bin/pip install klaus-assistant
.venv-klaus/bin/klaus
```

### First time launch

The first time launch guide sets up your API key, reading source, microphone, local speech model, and optional Obsidian vault.

Klaus may ask for these macOS permissions:

- **Microphone** for spoken questions.
- **Screen Recording** for Desk View and active-window images.
- **Accessibility** for global hotkeys and selected text.

You can deny Accessibility and use the buttons in Klaus. Questions about an active window may then use an image instead of selected text.

## What Klaus can do

- Read papers through Apple Desk View.
- Read selected text or capture the active window.
- Answer through one live GPT Realtime voice conversation.
- Stop an answer when you start speaking.
- Search, read, and append notes inside a configured Obsidian vault.
- Keep local reading sessions and conversation history.

## Use Klaus

### Read a paper

1. Open Apple Desk View.
2. Choose **Desk View: paper** in Klaus.
3. Frame the page and ask a question.

Desk View needs strong, even lighting to read small text.

### Read anything on screen

1. Open the content you want Klaus to read in any macOS app.
2. Choose **Active window** in Klaus.
3. Keep that window in front.
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

Klaus stores API keys in Apple Keychain. It stores settings and conversation history under `~/.klaus/`. It does not store captured page images in its database.

Provider use may incur charges. Read the [privacy notes](https://github.com/bgigurtsis/Klaus/blob/main/PRIVACY.md) before you connect accounts or private notes.

## Realtime cost estimate

Klaus currently uses `gpt-realtime-2.1`. OpenAI lists audio input at $32 per million tokens and audio output at $64 per million tokens in its [model documentation](https://developers.openai.com/api/docs/models/gpt-realtime-2.1). OpenAI bills user audio at one token per 100 milliseconds and assistant audio at one token per 50 milliseconds in its [Realtime cost guide](https://developers.openai.com/api/docs/guides/realtime-costs). That works out to about 600 input-audio tokens and 1,200 output-audio tokens per minute.

The estimates below cover raw audio only. They assume each question lasts 30 seconds and each answer lasts 60 seconds, unless noted otherwise. They exclude text context and captured page images, which can increase the bill.

| Usage pattern | Monthly use | Audio input | Audio output | Audio-only baseline |
|---|---|---:|---:|---:|
| Occasional reference | 20 questions per month | 10 min | 20 min | $1.73 |
| Regular study | 3 questions on each of 20 days | 30 min | 60 min | $5.18 |
| Heavy reading | 10 questions on each of 20 days | 100 min | 200 min | $17.28 |

The estimate uses $0.0192 per minute of user speech and $0.0768 per minute of Klaus speech. Longer answers can raise costs faster than longer questions. Later turns in one Realtime conversation can also include prior context, although cached input costs less.

## Settings

Open **Settings** in Klaus for normal changes. Advanced settings live in `~/.klaus/config.toml`.

| Setting | Default | Purpose |
|---|---:|---|
| `voice` | `cedar` | Choose the GPT Realtime voice |
| `camera_index` | `-2` | Use Desk View with `-2`, the active window with `-3`, or audio only with `-1` |
| `input_mode` | `voice_activation` | Use hands-free or push-to-talk input |
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
