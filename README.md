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
| Speech | Deepgram Flux streaming STT + TTS (async SDK) |
| Language model | Any OpenAI- or Anthropic-compatible endpoint, hosted or local |
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

A model running on your own machine works as well as a hosted one -- LM Studio,
Ollama and llama.cpp all speak the OpenAI wire, and LM Studio speaks the
Anthropic one too. Point `PERSONAE_LLM_BASE_URL` at it and give any value for
the key, since the app treats an empty key as "no model configured" while
local servers rarely check it.

Under Docker, `localhost` inside the container is the container, so the host is
reached by name instead:

```bash
PERSONAE_LLM_BASE_URL=http://host.docker.internal:1234/v1   # LM Studio
PERSONAE_LLM_API_KEY=local
PERSONAE_LLM_MODEL=nvidia/nemotron-3-nano-4b
```

LM Studio must also have "Serve on Local Network" enabled, or it binds to
loopback and the container cannot see it. Smaller models answer noticeably
faster, which matters more here than it would in a chat window: every second
before the first word is a second of silence in a conversation.

Three LM Studio settings matter for a conversation. Keep the model's
*thinking* mode off: reasoning before the first token is silence before the
first word. Try *speculative decoding* with a small draft model from
the same family (a Qwen3.5 0.8B under a Qwen3.5 9B, say): on a laptop it can
lift the token rate, which is what bounds how quickly each sentence is ready
to speak, though the gain on conversational text is smaller than on code, so
measure it. And load a vision-capable model with `PERSONAE_LLM_WIRE=anthropic`
if you want the camera: LM Studio's `/v1/messages` carries the picture.

Speech runs on Flux, Deepgram's voice-agent line: it judges when a turn has
ended from the words themselves rather than from a fixed silence, which is both
quicker and harder to fool than timing a pause. `PERSONAE_EOT_THRESHOLD` is the
one worth tuning — raise it and she waits longer but clips fewer words off the
end of your sentence. Flux also says when a turn has *probably* ended, a beat
before it is sure; set `PERSONAE_EAGER_EOT_THRESHOLD` and she drafts her
answer from that moment, throwing it away if you carry on. Leave it off with a
local model: it fires on a breath between words, and a local server keeps
generating an abandoned draft after the request is dropped, so the real reply
waits behind it. A hosted model that cancels cleanly gains a beat on every turn.

The recogniser is told to expect the character's name and anything in the
pack's `keyterms`, which is what stops "Wren" arriving as "Ren" or "Ryan".
Each turn is logged with how it ended and how loud the input was, so a quiet
microphone or a noisy room shows up in `docker compose logs backend` rather
than as her not listening.

Her voice is one socket held open for the whole conversation, and every
sentence is a turn on it: connecting costs more than a sentence does, so it
happens once rather than before each line.

Flux speaks English only. For anything else set `PERSONAE_STT_LANGUAGE` with a
`nova` model and a matching `aura-2` voice: Deepgram transcribes over a hundred
and forty languages and synthesises seven, though not all on every model —
Spanish and French need `nova-2` where German and Japanese work on `nova-3`. A
pairing that would fail is refused at startup rather than at the socket, and so
is a `flux` voice asked to speak something other than English. See
`.env.example`. A character pack that names its own voice overrides
`PERSONAE_TTS_VOICE`.

## Running under Docker

```bash
cp .env.example .env      # optional; it runs without keys
docker compose up -d --build
```

Then open <http://localhost:47465>.

### What comes up

Two containers. The **frontend** serves the built app through nginx and proxies
the conversation to the **backend**, which stays inside the compose network and
is never published. One port reaches everything, and the API and websocket are
same-origin, so there is no CORS to configure.

| | |
|---|---|
| Published port | `47465`, or whatever `PERSONAE_PORT` is set to |
| Restart policy | `unless-stopped` — survives a crash or a reboot |
| Health checks | Both containers; compose waits for the backend before starting the frontend |
| Credentials | `.env` is read at run time and never baked into an image |

### Everyday commands

```bash
docker compose ps                  # what is running, and whether it is healthy
docker compose logs -f backend     # follow the conversation logs
docker compose up -d backend       # after changing .env
docker compose up -d --build       # after changing code
docker compose down                # stop everything
```

Changing `.env` needs the container *recreated*, not restarted: compose
copies the values into the container's environment when it creates it, and
`restart` reuses that container with the environment it already has.
Changing code needs a rebuild.

### Publishing elsewhere

```bash
PERSONAE_PORT=8080 docker compose up -d
```

### Talking to a model on your own machine

Inside a container `localhost` is the container, so a model server running on
your machine is reached by name instead. The compose file maps
`host.docker.internal` to the host for exactly this:

```bash
PERSONAE_LLM_BASE_URL=http://host.docker.internal:1234/v1   # LM Studio
PERSONAE_LLM_API_KEY=local
PERSONAE_LLM_MODEL=nvidia/nemotron-3-nano-4b
```

LM Studio also needs "Serve on Local Network" enabled, or it binds to loopback
and the container cannot see it. Vision needs the Anthropic wire: set
`PERSONAE_LLM_WIRE=anthropic` and load a vision-capable model, and the camera
works locally; on the OpenAI wire it goes quiet and voice is unaffected.

### If something is wrong

**The page loads but she never answers.** Check the backend is healthy with
`docker compose ps`, then `docker compose logs backend` — a missing or wrong
credential is reported at startup, naming the variable.

**She cuts you off, or waits too long.** Every turn is logged with how it
ended: `ended by model at 0.86` is the recogniser deciding you had finished,
`ended by timeout` is the pause limit. Raise `PERSONAE_EOT_THRESHOLD` if she
jumps in on your pauses; lower it if she waits too long after you stop.
`input peak` on the same line is how loud you reached her.

**The websocket closes as soon as it opens.** Almost always a proxy in front of
this one that is not passing `Upgrade` and `Connection` headers.

**Changes to `.env` did nothing.** It is copied in when the container is
created: `docker compose up -d backend`. A restart is not enough -- it brings
the same container back with the environment it already had.

## Live conversation

The microphone stays open. The model decides when you have stopped speaking, so nothing is
held down, and it is patient by default: it waits until it is sure you have finished, and
lets a pause of several seconds go by mid-thought before taking the turn. Talking over a
reply cuts it short: the recogniser is read the whole time she is speaking, so your words
stop her on the server, and a fragment made only of words she has just said is taken to be
her own voice coming back through the microphone rather than you. The browser also stops
playback locally as soon as it hears a voice over hers. Echo cancellation is on; a headset
makes all of this cleaner.

Switch the camera on and a still from the moment you spoke is attached to that turn, so she
can answer questions about what is in front of you. This needs a language endpoint that
accepts images: see `PERSONAE_LLM_WIRE` in `.env.example`.

An interrupted reply is remembered as only what was actually said aloud, so her next answer
never refers to words you did not hear. History is a bounded window of recent turns.

## The avatar

Characters are rendered as 3D [VRM](https://vrm.dev/) models. Gestures drive arm, head, and
torso poses; emotions map onto VRM expression presets; and the mouth follows the loudness of
the audio being played, so speech stays in sync by construction rather than by timing.

A gesture is timed as well as posed: the hands prepare, strike on the first word her
voice stresses, hold, and beat on later stresses, and between gestures they wait up
rather than dropping to her sides. Where a model lacks the brow expressions the accents
are drawn with, they ride the `surprised` preset instead, and the console says so once.

### Authored motion

A held pose can put a hand where a wave belongs; it cannot make the wave. Drop
[VRM Animation](https://vrm.dev/en/vrma/) clips in `apps/frontend/public/motions/`
and list them in `index.json` there, keyed by gesture:

```json
{ "gesture-wave": "wave.vrma", "gesture-namaste": "namaste.vrma" }
```

A clip drives only the arms and hands; the head, breath and face stay procedural.
Any gesture without a clip stays procedural too. Clips are not committed -- they carry
their own licences; the [VRoid Project](https://vroid.com/en/news/6HozzBIV0KkcKf9dc1fZGW)
publishes a free set that includes a greeting.

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
