# Module boundaries and naming

Python modules use `snake_case`. React components use `PascalCase.tsx`, hooks
use `useCamelCase.ts`, and other TypeScript modules use `kebab-case.ts`.
Tests follow the module or behavior they exercise. Standard entry points
(`main`, `__main__`) and package-scoped `models`, `settings`, and `protocol`
retain their conventional names. Imports target canonical modules, not aliases.

## Backend

- `main.py`: application composition, HTTP and WebSocket transport.
- `settings.py`: typed environment configuration.
- `experience.py`: validate deployment-owned character/appearance selections.
- `voices.py`: apply the selected provider's configured voice to a session character.
- `providers/status.py`: runtime speech-provider status from selected credentials.
- `providers/factory.py`: construct adapters and optional alignment decorators.
- `providers/base.py`: provider protocols and shared provider contracts.
- `providers/<provider>[_<family>]_<stt|tts>.py`: vendor speech adapters.
- `providers/<wire>_compatible_llm.py`: LLM adapters named for API compatibility,
  not the model vendor behind the endpoint.
- `live_session.py`: input, listening/reconnect, turn arbitration, interruption,
  speculative replies, session-level speaker ownership, and history commits.
- `reply_generation.py`: generate a single reply; stream tokens and synthesis
  concurrently and close both tasks on failure or cancellation. The session
  retains ownership of the shared speaker; reply cancellation must not cancel
  its connection task.
- `conversation_history.py`: bounded conversation history.
- `sentence_buffer.py`, `speech_text.py`: streaming segmentation and spoken-text
  preparation, independent of vendor clients.
- `speech_events.py`, `lip_alignment.py`: provider-neutral timing and optional
  alignment decoration.
- `packs/`: validated character schema and pack discovery.

Provider dependencies are injected through protocols. Keep configuration
resolution separate from provider construction and network I/O. Do not add a
service locator or generic manager layer around these responsibilities.

## Frontend

- `App.tsx`: conversation presentation and loading deployment configuration.
- `experience-config.ts`: validate character and deployment API data.
- `avatar/config.ts`: validate renderer assets and mouth mappings only.
- `useConversation.ts`: bind conversation events and playback to React state.
- `conversation-resources.ts`: own capture, socket, player and AudioContext;
  invalidate stale startup callbacks before releasing resources. Cleanup is
  idempotent and continues if one device fails to close.
- `conversation-socket.ts`, `protocol.ts`: transport and validated wire messages.
- `audio/`: capture, playback, interruption detection, and speech timing.
- `avatar/`: rendering, rig application, and focused motion controllers.

Microphone samples and animation-frame features stay outside React state.
Captions and gestures follow the playback clock rather than network arrival.
Keep tests for delayed microphone permissions, teardown, interruption, queued
playback, failed provider connections, and speculative cancellation when
changing these boundaries. No live latency or acoustic guarantee follows from
passing unit tests.
