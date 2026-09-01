# Personae AI

Real-time voice avatars that listen, think, and speak — with gestures and expression driven
by the conversation.

*Personae* — the masks an actor wears. Each character is a mask the system puts on: a voice,
a temperament, and a vocabulary of gesture, defined entirely in data.

Speak into your mic; the browser streams audio to a Python backend that transcribes it,
answers in a character's voice, and streams speech back with matching gesture and emotion
cues for the avatar to perform.

> **Status:** early development. The architecture and tooling are in place; the pipeline is
> being built in vertical slices. See [Roadmap](#roadmap).

## Why this exists

Most voice-assistant demos are request/response: you finish talking, you wait, a reply
arrives. This project is about the harder, more interesting version — a *streaming* loop
where transcription, thinking, and speech overlap, and where the avatar's body language is
part of the response rather than decoration bolted on afterwards.

## Characters are masks, not code

Characters are **original archetypes** — an armored inventor, a storm-caller, a tactician —
each defined by a TOML file, not a branch in the code. A character declares its persona,
voice, colour theme, and the closed vocabulary of gestures and emotions it is allowed to
express.

Adding a character means adding a file. It never means editing the pipeline.

This repository ships no third-party intellectual property, and contributions must not
introduce any. Personal or licensed character packs belong in `packs/local/`, which is
gitignored. See [docs/character-packs.md](docs/character-packs.md).

## Runs without API keys

Speech-to-text, the language model, and text-to-speech sit behind narrow interfaces with
**mock implementations as the default**. Clone the repo, install, and it runs — the full
test suite passes with no credentials and no network. Supplying real keys swaps the
providers; no other code changes.

This is a deliberate constraint: an open-source project that can only be run by someone
holding paid credentials cannot really be contributed to.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.13, FastAPI, WebSockets, `uv` |
| Speech | Deepgram streaming STT + TTS (async SDK) |
| Language model | Any OpenAI-compatible endpoint |
| Frontend | React 19, TypeScript, Vite |
| Audio | Web Audio API — AudioWorklet capture, clock-scheduled playback |
| Quality | Ruff, mypy (strict), pytest, Vitest, ESLint |

Every version is pinned against what the registries actually publish, not what looked
current at the time of writing.

## Architecture

```
Browser
  │  AudioWorklet captures mic → PCM frames
  │  WebSocket  ws://localhost:8000/ws/session/{character_id}
  ▼
FastAPI
  ├─ SttProvider    streaming transcription
  ├─ LlmProvider    character persona + running transcript
  ├─ Expression     infers gesture/emotion, constrained to the
  │                 character's declared vocabulary
  └─ TtsProvider    streams speech audio back
  │
  ▼
Browser schedules audio on the AudioContext clock; avatar performs
the gesture/emotion cues alongside playback.
```

The expression stage is constrained by the character's own vocabulary, so the backend can
never emit a gesture the frontend has no animation for.

## Getting started

**Prerequisites:** Python 3.12+ with [`uv`](https://docs.astral.sh/uv/), Node 20+.
No API keys required.

```bash
git clone https://github.com/indranandjha1993/personae-ai.git
cd personae-ai
cp .env.example .env      # optional — defaults run on mock providers

# Backend
cd apps/backend && uv sync && uv run uvicorn personae.main:app --reload --ws websockets-sansio

# Frontend (separate terminal)
cd apps/frontend && npm ci && npm run dev
```

Open <http://localhost:5173>.

To use real services, set `DEEPGRAM_API_KEY` and your LLM endpoint in `.env` and switch the
provider settings from `mock` to `live`.

### Docker

```bash
docker compose up --build
```

## Development

```bash
# Backend
uv run pytest              # tests
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy .              # strict type check

# Frontend
npm test
npm run lint
npm run typecheck
```

Tests are written before implementation, and CI runs the full suite on Python 3.12 and 3.13
for every push and pull request.

## Roadmap

- [x] Repository, licensing, and contributor tooling
- [ ] Typed configuration and character-pack loader
- [ ] Provider interfaces with mock implementations
- [ ] WebSocket session protocol
- [ ] Vertical slice: mic → backend → audio response
- [ ] Deepgram STT/TTS and LLM providers
- [ ] Gesture and emotion inference
- [ ] Avatar rendering and lip-sync

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for
conventions, and please keep the two hard rules in mind: no third-party character IP, and
nothing that makes the project unrunnable without API keys.

## License

[MIT](LICENSE) © Indra Nand Jha
