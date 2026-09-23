# Speech and rendering integration

Personae keeps React/Vite, FastAPI, Deepgram STT, and the provider boundaries.
OpenRouter uses `PERSONAE_LLM_BASE_URL=https://openrouter.ai/api/v1`, the existing
`PERSONAE_LLM_API_KEY`, and a current model ID in `PERSONAE_LLM_MODEL`. Select
`PERSONAE_LLM_WIRE=openai`; enable `PERSONAE_LLM_VISION=true` only for models that
accept images. Existing credentials are never rewritten by this change.

## Speech providers and facial timing

`PERSONAE_TTS_PROVIDER=elevenlabs` selects the optional ElevenLabs adapter. Set
`PERSONAE_ELEVENLABS_TTS_API_KEY` and `PERSONAE_ELEVENLABS_TTS_VOICE`; the model defaults to
`eleven_flash_v2_5` and is configurable. A pack may override the voice using
`provider_voice="elevenlabs:VOICE_ID"`. Deepgram pack voice names do not get sent
to ElevenLabs. Without the selected provider's key the voice remains a mock.

ElevenLabs uses its [stream-with-timestamps endpoint](https://elevenlabs.io/docs/api-reference/text-to-speech/stream-with-timestamps).
The session reuses an HTTP client; cancellation closes the active response. Full
phrases are already available, so this does not require a second text WebSocket.
Its character alignment is transported separately from visemes. Letters are never
misrepresented as phonemes. The ordinary renderer still uses spectral mouth motion
unless an audio analysis provider supplies actual mouth cues.

For an optional timed-mouth mode, install [Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync)
on the backend host and set:

```dotenv
PERSONAE_LIP_SYNC=rhubarb
PERSONAE_RHUBARB_PATH=/absolute/path/to/rhubarb
PERSONAE_RHUBARB_RECOGNIZER=phonetic
```

Use `pocketSphinx` for English with its bundled recognizer resources. The executable
is not downloaded automatically or included in the Docker image. Rhubarb analyzes
one complete phrase, capped at 30 seconds, then its mouth shapes are reduced to
VRM vowel/closed channels. It adds buffering and CPU latency; benchmark it against
`audio` before using it for live conversation. It is an audio-derived timing option,
not film-quality facial capture or a 52-channel ARKit solver. Mock providers bypass
this optional dependency. Timeout/interruption kills the analysis process and
removes temporary audio/text files.

The server sends:

1. `speech_start { utterance_id }` before each phrase.
2. `speaking { text }` and the existing expression cue.
3. Optional `speech_timing { utterance_id, alignment, visemes }`.
4. Binary signed 16-bit little-endian mono PCM at the `ready.sample_rate` (24 kHz).

Each alignment entry is `{ start, end, text }`; each viseme is
`{ start, end, value, weight }`. Times are seconds from that utterance's first audio
sample. Canonical channels are `aa`, `ih`, `ou`, `ee`, `oh`, `closed`; weight is 0–1.
Timed providers yield `SpeechChunk`; older providers can still yield raw bytes.
The browser maps source time onto each chunk's scheduled AudioContext time, so
network stalls do not advance the mouth through unheard audio. Interrupted cues
and pending captions are cleared with playback. Unknown/cancelled utterance IDs
cannot add cues to the next utterance. Audio-driven animation remains the fallback.

## Character assets

```toml
[avatar]
renderer = "vrm"
model_url = "/models/licensed-portrait.vrm"
motions_url = "/motions/portrait/index.json"
hidden_meshes = [] # Exact mesh names, optional

[avatar.mouth_map]
aa = "aa"
ih = "ih"
ou = "ou"
ee = "ee"
oh = "oh"
# closed = "mouthClosed" # Only if authored in this model
```

URLs are local absolute paths or HTTPS. A VRM humanoid and named VRM expressions
are required; arbitrary ARKit GLBs are not automatically retargeted. Motion clips
remain optional VRMA files. Skin textures now retain their authored colors; the
previous model-specific tint and mesh-name regex have been removed.

For a visual acceptance prototype, supply one licensed asset, verify mouth closure,
eye movement, teeth/tongue, lighting, gesture collisions and framing, then measure
on the actual target phone and desktop. Record asset license, triangle count,
texture budget and missing expressions. No licensed photorealistic asset is bundled.

## Unreal / Pixel Streaming deployment boundary

For a separately hosted player, a local pack can select:

```toml
[avatar]
renderer = "pixel-streaming"
player_url = "https://your-player.example/personae"
```

The frontend embeds that player and passes `?character=pack/character`. The hosted
player owns its Start/End controls, microphone and media session. Personae does not
also start local audio or microphone capture in this mode. The iframe receives
microphone/autoplay/fullscreen permissions, but no API credentials or access token.
Configure authentication in the hosted player/server, never in a public pack URL.

This is an integration boundary, **not a deployed Unreal application**. The future
deployment needs Epic's matching-version Pixel Streaming frontend/signaling stack,
TURN where required, a licensed Unreal character, and a bridge with this contract:

- Allocate one isolated conversation/render state per independent user.
- Forward 16 kHz microphone PCM to `/ws/live/{pack}/{character}`.
- Feed backend PCM into Unreal playback and drive facial/gesture cues from that
  same playback position; emit the rendered video and sound together over WebRTC.
- Translate the semantic gesture/emotion vocabulary into the Unreal animation rig.
- On interruption clear Unreal audio, animation cues and queued media promptly.
- Reclaim sessions on disconnect; bound idle time, GPU capacity and queue length.

A stock Epic demo player can display a stream here, but will not animate or converse
with Personae until that bridge exists. Rendering browser-side facial cues against
an independently delayed remote video stream is deliberately avoided.
See [Epic's hosting guide](https://dev.epicgames.com/documentation/en-us/unreal-engine/hosting-and-networking-guide-for-pixel-streaming-in-unreal-engine).
GPU hosting, licensed assets and the Unreal bridge require the future deployment;
none are provisioned by this repository change.

## Measurements and acceptance

Run the reproducible mock pipeline baseline from `apps/backend`:

```sh
uv run python -m personae.benchmark --turns 10
```

To compare configured live LLM/TTS providers (billable requests):

```sh
uv run python -m personae.benchmark --turns 20 --live
```

This benchmark uses a fixed transcript and reports p50/p95 for first token,
first speakable phrase, first PCM and completed generation. It excludes STT,
network transport, output-device latency and actual audibility. Each turn opens
a session; retain this cold-session condition when comparing providers.

Open the app with `?diagnostics` and use **Download measurements** after talking.
Measurements remain in memory (last 200 samples per metric), contain no speech
or keys, and are also emitted as `personae:metric` DOM events. Browser metrics:

- `transcript_to_scheduled_audio_ms`: final transcript receipt to scheduled first
  sample, including the playback lead. Does not measure speech-end detection or
  hardware output latency; leading silence still counts as scheduled audio.
- `local_interrupt_stop_ms`: local stop/clear work after interruption is detected,
  not speech onset to detection latency.
- `render_frame_ms`: one frame-time sample per second; not a full-frame FPS trace.
- Server first-token/phrase/audio/generation metrics are relative to generation
  start, which may precede turn confirmation with eager drafting enabled.

For production acceptance, collect at least 100 turns per provider/device/network,
measure speech end and actual audible onset from a loopback recording, and report
p50/p95, interrupt detection delay, underruns and manually scored lip-sync quality.
Compare the same utterances, voice, model, region and rendering asset. A sub-800ms
response is a target to validate, not a guarantee of this implementation.

Cost baseline: record provider-billed LLM input/output tokens, TTS characters or
credits, STT minutes, and GPU/egress charges for the same session duration. Divide
total cost by conversation minutes. This version does not infer billed usage from
streaming text or publish a price estimate; rates and GPU packing require actual
provider/deployment data. Photorealism, live latency and costs remain unmeasured
until credentials, a licensed asset and target hardware/deployment are supplied.

## Server-owned character configuration

The browser has no personality, appearance, voice or quality selectors. Configure
these in the repository `.env`:

```dotenv
PERSONAE_CHARACTER_ID=bundled/mentor
PERSONAE_APPEARANCE_ID=bundled/seed
PERSONAE_VOICE_ID=default
PERSONAE_RENDER_QUALITY=auto
```

`CHARACTER_ID` selects a pack personality: `bundled/seed` (Wren),
`bundled/mentor` (Sage), or `bundled/analyst` (Atlas). For custom prompts, add a
character under `packs/local` and select its qualified ID. `APPEARANCE_ID` selects
another pack's avatar; leave blank to use the personality's own avatar. The three
bundled characters currently share one VRM model. Hosted characters manage their
own appearance and voice; leave appearance blank for those deployments.

`VOICE_ID=default` uses the selected `TTS_PROVIDER` and character pack voice.
`deepgram:default` explicitly uses `PERSONAE_DEEPGRAM_TTS_VOICE`, `elevenlabs:default` uses
`PERSONAE_ELEVENLABS_TTS_VOICE`, and `local:af_heart` selects a configured local voice.
Only IDs available for configured providers are accepted; invalid IDs fail startup.
Credentials and personality prompts stay on the backend.

Low quality caps device pixel ratio at 1; Auto at 1.5; High at 2. Auto is a
resolution cap, not an adaptive performance benchmark. The avatar supports retry
after load failure or lost WebGL context.

After editing `.env`, recreate the backend with
`docker compose up -d --force-recreate backend`, then refresh the browser.
A plain Docker restart does not reload `env_file` values. For development outside
Docker, restart the backend process. Backend and frontend must both be updated
for this version's experience configuration response.

## Local voice development

Run a compatible local speech server such as
[Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI), then set
`PERSONAE_LOCAL_TTS_BASE_URL=http://localhost:8880/v1`. When the backend runs in
Docker and the speech server runs on the host, use `host.docker.internal` instead.
Set `PERSONAE_LOCAL_TTS_VOICES=["af_heart","af_bella"]` to the installed voices.
The public catalogue only exposes configured voice IDs, never credentials or
server URLs. Select one through `PERSONAE_VOICE_ID`. Set `PERSONAE_TTS_PROVIDER=local` for the default voice to use it.
The server must return raw mono PCM16 at 24 kHz for `response_format=pcm`.
An unavailable configured server reports an error; it does not invoke a paid fallback.

This adapter is tested against simulated HTTP responses, not a live Kokoro instance.
Local inference uses your hardware and electricity. It does not make hosted GPUs
free, install a model server, replace STT, or turn a stylized VRM into a film-quality
asset. Existing STT/LLM provider configuration still applies.

## Environment naming

Provider settings use `PERSONAE_<PROVIDER>_<STT|TTS>_<SETTING>`.
For example, `PERSONAE_DEEPGRAM_STT_MODEL`, `PERSONAE_DEEPGRAM_TTS_VOICE`,
and `PERSONAE_ELEVENLABS_TTS_MODEL`. `PERSONAE_DEEPGRAM_API_KEY` is shared by
Deepgram STT and TTS. Provider-independent choices retain names such as
`PERSONAE_TTS_PROVIDER` and `PERSONAE_CHARACTER_ID`.

## Session recovery

The page shows Connecting until the socket handshake, microphone capture and
playback context are ready. A connection taking more than 20 seconds offers a
restart. A reply stalled for 45 seconds, or a playback clock frozen for 10
seconds while audio is queued, ends the session with an actionable error.
Silence while listening is normal and does not time out a conversation.

If `PERSONAE_ACCESS_TOKEN` is configured, open the page with `?token=<your-token>`;
the browser forwards that explicit token to its conversation WebSocket. Do not
publish that URL or embed the server token in frontend build variables.

## Full-duplex audio in noisy rooms

Keep `PERSONAE_BARGE_IN_ENABLED=true` to listen while the avatar speaks and
interrupt replies. With a nearby headset microphone, `PERSONAE_MICROPHONE_AUTO_GAIN=false`
avoids requesting automatic amplification of quieter input. Echo cancellation
and noise suppression are requested independently and remain on.

Open the page with `?diagnostics` and select Download measurements after starting
a conversation. The local JSON includes the microphone label and the processing
settings reported by the browser. `null` means the browser did not report that
setting; it does not prove the feature is enabled. Confirm the microphone label
matches the headset, not the laptop. These diagnostics contain no recorded audio.

Browser noise suppression is not speaker identification. TV dialogue can still
be transcribed and cause interruptions, especially when it is as clear as the
user's speech. A volume threshold or generic speech detector cannot reliably
distinguish them; this needs testing with the actual room and microphone.

`PERSONAE_BARGE_IN_ENABLED=false` remains an explicit opt-in for turn-taking:
microphone audio is replaced with silence during replies. It is not the recommended
setting when interruption is required.
