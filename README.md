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

Speech-to-text, the language model, and text-to-speech sit behind narrow interfaces, and
each falls back to a **stand-in when its credential is absent**. Clone the repo, install,
and it runs — the full test suite passes with no credentials and no network. Adding a key
is the only step needed to make that stage real.

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
  │  WebSocket  ws://localhost:8000/ws/live/{pack}/{character}
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

**Prerequisites:** Python 3.13+ with [`uv`](https://docs.astral.sh/uv/), Node 22.22+.
No API keys required.

```bash
git clone https://github.com/indranandjha1993/personae-ai.git
cd personae-ai
cp .env.example .env      # optional — it runs without any keys

# Backend
cd apps/backend && uv sync && uv run uvicorn personae.main:app --reload --ws websockets-sansio

# Frontend (separate terminal)
cd apps/frontend && npm ci && npm run dev
```

Open <http://localhost:5173>.

If port 8000 is already taken, run the backend elsewhere and point the dev server at it:

```bash
uv run uvicorn personae.main:app --port 8100 --ws websockets-sansio   # backend
PERSONAE_BACKEND=http://127.0.0.1:8100 npm run dev                    # frontend
```

To use real services, copy `.env.example` to `.env` and add your keys:

```bash
PERSONAE_DEEPGRAM_API_KEY=your-key          # transcription and speech

PERSONAE_LLM_API_KEY=your-key               # the language model
PERSONAE_LLM_BASE_URL=https://api.openai.com/v1
```

A key is all that is needed — each stage goes live when its credential is present and falls
back to a stand-in when it is not, so you can run real speech against a stand-in model, or
the reverse, without setting anything else. A key with no endpoint fails at startup naming
what is missing, rather than quietly falling back.

The speech model, fallback voice, and turn-taking timings are configurable too — see
`.env.example`. `PERSONAE_ENDPOINTING_MS` is the one worth tuning: it sets how long she
waits through a pause before deciding you have finished speaking. A character pack that
names its own voice overrides `PERSONAE_TTS_VOICE`.

### Docker

```bash
docker compose up --build
```

## Live conversation

The microphone stays open. Deepgram decides when you have stopped speaking, so nothing is
held down, and talking over a reply cuts it short — input counts as speech only while she is
actually speaking and only when it is clearly louder than what is playing, so the reply
leaking back through the microphone does not interrupt her.

Switch the camera on and a still from the moment you spoke is attached to that turn, so she
can answer questions about what is in front of you. This needs a language endpoint that
accepts images: see `PERSONAE_LLM_WIRE` in `.env.example`.

An interrupted reply is remembered as only what was actually said aloud, so her next answer
never refers to words you did not hear. History is a bounded window of recent turns.

## The avatar

Characters are rendered as 3D [VRM](https://vrm.dev/) models. Gestures drive arm, head, and
torso poses; emotions map onto VRM expression presets; and the mouth follows the loudness of
the audio being played, so speech stays in sync by construction rather than by timing.

**No model ships with the project.** VRM files are large and carry their own licences, so
supply one yourself:

1. Get a `.vrm` model -- [VRoid Hub](https://hub.vroid.com/) has free avatars, and
   [VRoid Studio](https://vroid.com/en/studio) lets you make your own.
2. Save it as `apps/frontend/public/avatar.vrm`.
3. Reload the page.

Until then the viewport explains what is missing and the conversation still works. The 3D
stack is loaded on demand, so the initial bundle is unaffected if you never add a model.

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

Tests are written before implementation, and CI runs the full suite on Python 3.13 and 3.14, on both Linux and macOS
for every push and pull request.

## Roadmap

- [x] Repository, licensing, and contributor tooling
- [x] Typed configuration and provider interfaces
- [x] Character-pack loader
- [x] Mock provider implementations
- [x] WebSocket session protocol
- [x] Vertical slice: browser mic → backend → audio playback
- [x] Deepgram STT/TTS and LLM providers
- [x] Gesture and emotion inference (vocabulary-constrained)
- [x] Avatar rendering and lip-sync
- [x] Live conversation with barge-in
- [x] Camera input for questions about what you are holding

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for
conventions, and please keep the two hard rules in mind: no third-party character IP, and
nothing that makes the project unrunnable without API keys.

## License

[MIT](LICENSE) © Indra Nand Jha
