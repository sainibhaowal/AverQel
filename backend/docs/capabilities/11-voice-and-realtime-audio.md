# Voice and realtime audio implementation

**Status:** implemented locally; external deployment and real-device verification
remain release gates.

This implementation guide describes AverQel voice behavior based on the
backend, frontend, Compose, LiveKit configuration, and recorded local evidence.
Use the [release index](../release/03-current-worktree-change-index.md) for
the latest checked source and deployment status. This guide replaces the
former `assets/Voice-setup.md` planning note.

## 1. What voice currently does

AverQel voice provides two user-facing modes:

- **Dictate to composer:** speech is transcribed into the DeepSpace composer
  for review and manual submission.
- **Voice conversation:** speech is submitted through the normal DeepSpace chat
  stream for the currently selected conversation. New visible assistant text
  is spoken through the active LiveKit audio room while the request runs.

Voice is an optional interface around DeepSpace. It does not replace the normal
authenticated chat API, SSE stream, queue, provider selection, or durable
conversation storage.

Current user flow:

~~~text
User enables Dictate to composer
  -> browser requests authenticated voice token
  -> browser joins a LiveKit room
  -> browser publishes microphone audio
  -> voice-agent receives audio
  -> Silero VAD detects speech
  -> Faster-Whisper transcribes speech
  -> voice-agent publishes dictation-result
  -> browser inserts text into the composer
  -> user submits the normal DeepSpace chat request

User enables Voice conversation
  -> browser enables microphone and TTS in the same LiveKit room
  -> voice-agent transcribes a final speech turn
  -> browser submits it through the selected DeepSpace conversation
  -> selected DeepSpace provider and tools run through the normal chat API/SSE stream
  -> browser forwards complete visible sentences from that live stream
  -> voice-agent queues the text in order
  -> Kokoro synthesizes audio
  -> voice-agent publishes an audio track
  -> browser plays the track
~~~

The Dictate to composer mode does not submit transcripts. Voice conversation
does submit each final transcript as a normal DeepSpace chat turn. Both modes
use the same room-scoped authenticated token and the existing DeepSpace
authorization, provider selection, tool approval, and durable queue behavior.

Voice conversation speaks only new visible `delta` text from the active browser
stream. It does not replay saved chat history, speak `thinking` events, read raw
tool payloads, or call a second chat provider to generate announcements. A
pending sentence is flushed when a tool starts or the DeepSpace turn completes.
When a tool starts and no snippet was spoken in the previous four seconds, the
browser may send one brief, generic progress line. It is selected from the
known tool category and does not include the tool name, arguments, or result.
Kokoro uses the `am_michael` voice preset. Speaking again cancels the current
playback and queued snippets, but does not cancel the DeepSpace tool run.

## 2. Architecture

~~~mermaid
flowchart LR
    Browser[DeepSpace browser client]
    Composer[DeepSpace composer]
    API[Authenticated AverQel API]
    Token[Voice token route]
    LK[LiveKit server]
    Agent[voice-agent worker]
    VAD[Silero VAD]
    STT[Faster-Whisper STT]
    Provider[Selected DeepSpace chat provider]
    TTS[Kokoro ONNX TTS]
    Audio[Browser audio track]

    Browser --> Token
    Token --> API
    Token --> Browser
    Browser -->|WebRTC microphone| LK
    Browser -->|WSS room connection| LK
    LK --> Agent
    Agent --> VAD
    VAD --> STT
    STT -->|dictation-result data| LK
    LK --> Browser
    Browser -->|dictation mode| Composer
    Browser -->|voice conversation transcript| API
    API -->|DeepSpace chat SSE| Browser
    Browser -->|visible delta snippets| LK
    Agent --> TTS
    TTS -->|audio track| LK
    LK --> Audio
~~~

### Service responsibilities

| Component | Responsibility |
| --- | --- |
| DeepSpaceChatClient | Starts/stops the browser room, keeps dictation separate from voice conversation, submits voice turns to the selected chat, and forwards live visible response text |
| DeepSpaceComposer | Displays voice state and dictation controls |
| GET /api/v1/voice/token | Issues an authenticated, room-scoped LiveKit token |
| LiveKit | WebRTC room and audio/data transport |
| voice-agent | Receives microphone audio, runs VAD/STT, serializes TTS playback, publishes state/audio |
| Silero VAD | Detects speech boundaries and reduces noise-triggered transcription |
| Faster-Whisper | Local speech-to-text |
| Selected DeepSpace chat provider | Handles the user request and tools through the normal chat API; its visible streamed answer is what voice mode speaks |
| Kokoro ONNX | Local text-to-speech synthesis |
| DeepSpace chat API/SSE | Continues to own normal user messages, agent execution, queueing, and answers |

## 3. Exact implementation map

### Backend

- backend/app/deepspace/integrations/voice_agent.py
  - LiveKit agent entrypoint.
  - Faster-Whisper loading.
  - Kokoro loading.
  - Silero VAD.
  - Partial and final transcription.
  - TTS audio-track publication.
  - Voice state data messages.
  - Speech playback interruption when new speech begins.
- backend/app/integrations/api/voice.py
  - GET /api/v1/voice/token.
  - Requires the queries:run permission.
  - Requires the requested identity to equal the authenticated user identity.
  - Issues room-join and room-scoped grants.
- backend/app/core/config.py
  - LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET settings.
- backend/docker-compose.yml
  - livekit service.
  - voice-agent service.
  - model mounts and internal LiveKit URL.
- backend/ops/livekit/livekit.yaml
  - Local LiveKit port, RTC ports, and local development key configuration.
- backend/requirements.txt
  - livekit, livekit-agents, livekit-plugins-silero,
    faster-whisper, and kokoro-onnx dependencies.

### Frontend

- frontend/app/dashboard/deepspace/_components/DeepSpaceChatClient.tsx
  - Dynamic livekit-client import.
  - Authenticated token request.
  - WSS/WS room connection.
  - Microphone enable/disable.
  - Dictation result insertion into the composer.
  - Voice transcript submission through `submitQuery` for the current conversation.
  - Live visible assistant sentence chunking and LiveKit `speak-text` messages.
  - TTS audio-track attachment and playback.
  - Voice state and status label handling.
- frontend/app/dashboard/deepspace/_components/DeepSpaceComposer.tsx
  - Dictation and voice conversation controls.
  - Listening, thinking, and speaking presentation.
- frontend/package.json
  - livekit-client dependency.

### Existing open-source components and license review

This change adds no dependency. It reuses the installed LiveKit and local
speech stack. Upstream source and model license notices must remain available
when distributing those components; model-weight terms are separate from
wrapper-library terms.

| Component | License reviewed |
| --- | --- |
| [LiveKit Agents framework](https://github.com/livekit/agents) | Apache-2.0 |
| [Faster-Whisper source](https://github.com/SYSTRAN/faster-whisper) | MIT |
| [Silero VAD source](https://github.com/snakers4/silero-vad/blob/master/LICENSE) | MIT |
| [Kokoro ONNX source](https://github.com/thewh1teagle/kokoro-onnx/blob/main/LICENSE) | MIT |
| [Kokoro-82M v1.0 model weights](https://huggingface.co/hexgrad/Kokoro-82M) | Apache-2.0 |

### Documentation and evidence

- backend/docs/release/01-end-to-end-handoff.md
  - Overall local voice status and deployment gates.
- backend/docs/release/02-production-e2e-verification.md
  - Recorded local HTTPS/WSS voice smoke evidence.
- backend/docs/deepspace/05-deepspace-operations-runbook.md
  - Operational verification and local voice smoke notes.
- frontend/app/documentation/features/page.tsx
  - User-facing capability description.
- frontend/app/documentation/architecture/page.tsx
  - Service architecture description.

## 4. Detailed runtime flow

### 4.1 Token and room connection

~~~mermaid
sequenceDiagram
    actor User
    participant UI as DeepSpaceChatClient
    participant API as /api/v1/voice/token
    participant LK as LiveKit
    participant VA as voice-agent

    User->>UI: Enable Dictate to composer or Voice conversation
    UI->>API: Request token with room and user identity
    API->>API: Authenticate user and require queries:run
    API->>API: Verify identity equals authenticated user
    API-->>UI: Room-scoped JWT
    UI->>LK: Connect over WSS/WS
    LK->>VA: Agent joins/receives room
    UI->>VA: Publish set-mode data
    VA-->>UI: listening/thinking/speaking state
~~~

The browser creates a short random DeepSpace room name and uses an identity
derived from the authenticated user. The API never returns LiveKit API
credentials to the browser; it returns only a signed room token.

Development defaults exist in configuration. Staging and production must
override them with deployment secrets and must not use development credentials.

### 4.2 Dictation

~~~mermaid
sequenceDiagram
    actor User
    participant Mic as Browser microphone
    participant LK as LiveKit WebRTC
    participant VA as voice-agent
    participant VAD as Silero VAD
    participant STT as Faster-Whisper
    participant UI as Composer
    participant API as DeepSpace chat API

    User->>Mic: Speak
    Mic->>LK: Audio frames
    LK->>VA: Remote audio track
    VA->>VAD: Speech frames
    VAD->>STT: Speech segment
    STT-->>VA: Partial transcript
    VA-->>LK: listening state/transcript
    LK-->>UI: Live transcript preview
    STT-->>VA: Final transcript
    VA-->>LK: dictation-result
    LK-->>UI: Insert text into composer
    User->>UI: Review/edit and send manually
    UI->>API: Submit normal DeepSpace message
~~~

Noise and low-amplitude audio are filtered before final transcription.
Whisper output is also filtered for silence probability, compression-ratio
hallucinations, low-confidence segments, and known static boilerplate.

### 4.3 Voice conversation output

~~~mermaid
sequenceDiagram
    participant UI as DeepSpaceChatClient
    participant LK as LiveKit
    participant VA as voice-agent
    participant API as DeepSpace chat API/SSE
    participant TTS as Kokoro
    actor User

    UI->>API: Submit final transcript to selected conversation
    API-->>UI: Stream new visible delta text and tool events
    UI->>UI: Buffer text to sentence boundaries
    UI->>LK: Send speak-text snippets from visible deltas
    LK->>VA: Queue snippets in order
    VA->>TTS: Synthesize next snippet
    TTS-->>VA: PCM samples
    VA->>LK: Publish agent audio track
    LK-->>User: Browser plays audio
~~~

The frontend forwards only live `delta` events from the selected DeepSpace
stream. It ignores private `thinking` events and tool payloads, skips fenced
code, and never walks saved messages to create audio. It flushes an unfinished
sentence when a tool starts so spoken model commentary can lead into the tool
work, then speaks later visible answer text as the stream continues. If no
snippet was spoken during the previous four seconds, a tool-start event can
also produce a brief generic status such as “I’m checking the latest sources
now.” The status does not read tool names, arguments, or results.

The voice agent queues snippets and plays them sequentially so a later sentence
does not interrupt the one currently being synthesized. User speech or turning
off voice conversation cancels the current snippet and clears queued snippets.
DeepSpace still owns the active chat run and its normal cancellation and queue
controls.

### 4.4 Barge-in

When the user begins speaking while the agent is speaking, the voice agent
cancels current TTS playback and clears pending voice snippets for that room.
Speaking state is tracked per room so activity in one user's session does not
interrupt another room.

It does not automatically cancel the active DeepSpace model/tool run or
rewrite the durable queue. DeepSpace cancellation, pause, resume, retry, and
steering remain owned by the existing DeepSpace queue and chat controls.

## 5. Security and privacy contract

Voice must preserve the existing application boundaries:

- The token route requires authentication and queries:run permission.
- The requested LiveKit identity must match the authenticated user.
- LiveKit API credentials remain server-side.
- Browser state contains room/token operation state, not provider secrets.
- Voice does not bypass DeepSpace authorization, tenant isolation, queue policy,
  provider selection, or tool approval.
- Audio transport uses the configured WSS/WS deployment route.
- Voice status messages must not include API keys, OAuth tokens, raw secrets, or
  private infrastructure details.
- Voice-agent logs record transcription lengths and state, not raw transcript
  text.
- Model paths are mounted read-only in the voice-agent container.
- The voice-agent is a separate service, not part of the API process.
- Normal chat history and queue persistence remain unchanged by voice mode.

## 6. Current capability versus the former setup note

| Former setup-note idea | Current reality |
| --- | --- |
| LiveKit WebRTC transport | Implemented locally |
| Faster-Whisper streaming-style transcription | Implemented locally with partial/final transcription |
| Kokoro TTS | Implemented locally |
| VAD and barge-in | Implemented for speech detection and TTS interruption |
| Voice state updates | Implemented through LiveKit data messages |
| New visible response sentences spoken while the DeepSpace request runs | Implemented locally |
| Voice transcript submitted to the current DeepSpace chat | Implemented locally |
| Previous chat history replayed when voice is enabled | Not performed |
| Hidden reasoning or raw tool results spoken | Not performed |
| Dictation into DeepSpace composer | Implemented |
| Full autonomous voice command center | Not the current default flow |
| Full ReactFlow live execution graph | Not verified in the current frontend |
| Voice automatically cancels/steers DeepSpace tools | Not implemented by the voice layer |
| Guaranteed response below 500 ms | Not measured or guaranteed |
| Physical microphone/device proof | Pending |
| External staging/VPS proof | Pending |

## 7. Local verification evidence

The release documents record the following local evidence dated 2026-09-23:

- LiveKit voice agent registered successfully after local credentials were
  aligned.
- API liveness and readiness remained healthy.
- An authenticated disposable browser session requested a voice token.
- The browser connected through HTTPS/WSS.
- Chromium fake microphone input reached the voice agent.
- STT became active.
- TTS published an agent audio track and completed local synthesis.
- The complete local backend/frontend verification was recorded separately.

This proves local service wiring and browser transport. It does not prove:

- a physical microphone on a real device;
- external staging/VPS networking;
- production TURN behavior;
- production certificates and proxy configuration;
- every browser's autoplay and microphone permission behavior;
- every provider's live voice configuration.

## 8. Production deployment requirements

Before enabling voice for a real deployment, verify:

1. LiveKit API key and secret are supplied through deployment secrets.
2. Development LiveKit credentials are not active.
3. HTTPS and WSS terminate at the intended public origin.
4. LiveKit RTC TCP/UDP and TURN configuration matches the deployment network.
5. The voice-agent has access to the required read-only STT/TTS model files.
6. The voice-agent registers successfully without repeated authentication errors.
7. The API token route returns 200 only for an authenticated authorized user.
8. A mismatched identity returns 403.
9. A disposable user can connect, dictate into the composer, edit, and submit.
10. In Voice conversation mode, a disposable user's final transcript reaches
    the currently selected DeepSpace chat and new visible response snippets
    play in order.
11. A second tenant cannot obtain or use the first tenant's room identity.
12. Closing/reloading the browser disconnects voice cleanly without cancelling or
    deleting unrelated DeepSpace work.
13. Physical microphone and browser-permission tests pass.
14. The service remains healthy after voice-agent restart.
15. Voice failures remain isolated from normal DeepSpace chat and queue behavior.

## 9. Known hardening items

The current local implementation should not be advertised as a fully autonomous
voice orchestration platform until these are addressed and tested:

- Bind voice-provider resolution to the authenticated room user and tenant.
  Voice output now uses the selected DeepSpace chat stream; the voice-agent
  does not resolve or call a separate chat provider.
- Add a dedicated authenticated voice E2E suite to the maintained test tree if
  the release smoke is currently only an external/scripted check.
- Add an explicit voice-session cleanup and lifecycle metric policy.
- Define TURN and public-network deployment configuration for staging/VPS.
- A direct audio-native speech-to-speech model is not part of this deployment.
  Any future integration must preserve the current DeepSpace conversation,
  tool approval, tenant, and queue boundaries.
- If a live execution graph is desired, implement it as a separate UI contract
  tied to durable DeepSpace events; do not infer it from voice state messages.

These are documented boundaries and hardening tasks. This document does not
silently change them.

## 10. Operational troubleshooting

| Symptom | Check |
| --- | --- |
| Voice token returns 403 | Auth session, queries:run permission, and identity format |
| Browser cannot connect | HTTPS/WSS proxy route, LiveKit URL, certificate, and RTC ports |
| Agent retries authentication | LiveKit key/secret match between server and voice-agent |
| No transcription | Browser microphone permission, room subscription, VAD, and STT model path |
| No TTS audio | TTS model/voice files, browser autoplay, audio track subscription |
| Voice works locally but not remotely | TURN, firewall, public hostname, certificates, and deployment environment |
| Normal chat fails after voice error | Treat as an isolation regression; voice must not own normal chat cancellation |

## 11. Source of truth

Use this document for current voice architecture and behavior. Use these
documents for release evidence and operations:

- release/01-end-to-end-handoff.md
- release/02-production-e2e-verification.md
- deepspace/05-deepspace-operations-runbook.md

The former assets/Voice-setup.md file was a planning note and has been
replaced by this verified implementation document.
