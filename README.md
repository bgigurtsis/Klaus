# Klaus

A voice-based research assistant for reading physical papers and books. Point your document camera at a page, hold **F2**, ask a question, and Klaus reads the page and answers in a natural speaking voice.

Uses Claude for vision and reasoning, OpenAI for speech-to-text and text-to-speech, and Tavily for web search when it needs to verify something.

## Quick Start

**You need:** Python 3.11+, a document camera (USB webcam on a stick), a microphone, and speakers.

```
git clone https://github.com/yourusername/Klaus.git
cd Klaus
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Add your API keys to `.env`:

| Key | Where to get it |
|-----|----------------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/) |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com/) (free tier: 1,000 searches/mo) |

Run it:

```
python -m klaus.main
```

## Usage

| Action | How |
|--------|-----|
| Ask a question | Hold **F2**, speak, release |
| Switch papers | Session dropdown (top-right) |
| Start a new paper | **+ New Session** |
| Replay an answer | Click the replay button on any response |

Place your paper under the camera before asking. Klaus captures the page when you release F2 and sends it along with your question to Claude. If Claude isn't sure about something, it searches the web first.

Each session keeps its own conversation history. Klaus also builds a knowledge profile across sessions so it can reference things you've studied before.

## Configuration

All settings are in `klaus/config.py`:

| Setting | Default | Notes |
|---------|---------|-------|
| `PUSH_TO_TALK_KEY` | `F2` | Global hotkey, works without app focus |
| `CAMERA_DEVICE_INDEX` | `0` | Change if you have multiple cameras |
| `TTS_VOICE` | `coral` | Options: coral, nova, alloy, ash, ballad, echo, fable, onyx, sage, shimmer, verse, cedar, marin |
| `SYSTEM_PROMPT` | *(see file)* | Klaus's personality and behavior rules |

## Architecture

```
Mic (push-to-talk) --> STT --\
                               --> Claude (vision + tools) --> TTS --> Speakers
Camera (live feed) ----------/        |
                                      +--> Tavily (web search)
                                      +--> SQLite (memory)
                                      +--> Chat UI
```

## Data & Cost

Database lives at `~/.klaus/klaus.db` (sessions, exchanges, knowledge profile). Delete it to start fresh.

| Usage | Approx. cost |
|-------|-------------|
| 10 questions | ~$0.06 |
| 50 questions | ~$0.30 |
| 100 questions/day | ~$3--4/day |

Largest cost driver is Claude (vision + context), not TTS.
