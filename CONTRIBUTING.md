# Contributing

Klaus may accept focused bug fixes and features for its supported macOS workflow.

## Set up the project

1. Install Python 3.11 through 3.13 and PortAudio.
2. Create a virtual environment with `python3.12 -m venv .venv`.
3. Activate it with `source .venv/bin/activate`.
4. Install Klaus with `python -m pip install -e '.[dev]'`.
5. Copy `.env.example` to `.env` only when you need live provider tests.

Unit tests must not require real API keys, devices, personal files, or network access.

## Make a change

Keep each change focused.
Add tests for changed behavior.
Do not commit `.env`, API keys, transcripts, databases, or model files.
Run `python -m pytest -q` before you submit a pull request.

For macOS app changes, run `./scripts/install-macos-app.sh` after the tests pass.
Verify that `$HOME/Applications/Klaus.app/Contents/Resources/source-root` contains your checkout path.

## Submit a pull request

Explain the problem and the chosen fix.
List the tests you ran.
Call out changes to provider data, local storage, permissions, or costs.
Keep unrelated changes out of the pull request.

By contributing, you agree that the project may distribute your contribution under the MIT License.
