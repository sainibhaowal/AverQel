# Voice and realtime audio implementation

**Status:** implemented locally; external deployment and real-device verification
remain release gates.

This implementation guide describes AverQel voice behavior based on the
backend, frontend, Compose, LiveKit configuration, and recorded local evidence.
Use the [release index](../release/03-current-worktree-change-index.md) for
the latest checked source and deployment status. This guide replaces the
former `assets/Voice-setup.md` planning note.

## 1. What voice currently does

AverQel voice currently provides two user-facing modes:

- Voice dictation: microphone speech is transcribed and placed into the
  DeepSpace composer.
- TTS commentary: a completed assistant response can be spoken through the
  active LiveKit audio room.

Voice is an optional interface around DeepSpace. It does not replace the normal
authenticated chat API, SSE stream, queue, provider selection, or durable
conversation storage.

Current user flow:

~~~text
User enables Dictation
  -> browser requests authenticated voice token
  -> browser joins a LiveKit room
  -> browser publishes microphone audio
  -> voice-agent receives audio
  -> Silero VAD detects speech
  -> Faster-Whisper transcribes speech
  -> voice-agent publishes dictation-result
  -> browser inserts text into the composer
  -> user submits the normal DeepSpace chat request

User enables TTS Commentary
  -> completed assistant message is selected in the browser
  -> browser sends test-tts data to the room
  -> voice-agent generates/uses spoken text
  -> Kokoro synthesizes audio
  -> voice-agent publishes an audio track
  -> browser plays the track
~~~

The current dictation path does not automatically submit every transcript as a
new chat request. The transcript is placed into the composer so the user can
review and edit it before sending.

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
    Provider[Configured AverQel chat provider]
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
    Browser --> Composer
    Browser -->|normal chat submit| API
    API -->|completed answer| Browser
    Browser -->|test-tts data| LK
    Agent --> Provider
    Provider --> Agent
    Agent --> TTS
    TTS -->|audio track| LK
    LK --> Audio
~~~

### Service responsibilities

| Component | Responsibility |
| --- | --- |
| DeepSpaceChatClient | Starts/stops the browser room, controls STT/TTS modes, receives transcripts and audio |
| DeepSpaceComposer | Displays voice state and dictation controls |
| GET /api/v1/voice/token | Issues an authenticated, room-scoped LiveKit token |
| LiveKit | WebRTC room and audio/data transport |
| voice-agent | Receives microphone audio, runs VAD/STT, generates TTS, publishes state/audio |
| Silero VAD | Detects speech boundaries and reduces noise-triggered transcription |
| Faster-Whisper | Local speech-to-text |
| Configured chat provider | Produces short spoken commentary text when required |
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
  - TTS audio-track attachment and playback.
  - Voice state and status label handling.
- frontend/app/dashboard/deepspace/_components/DeepSpaceComposer.tsx
  - Dictation and TTS control buttons.
  - Listening, thinking, and speaking presentation.
- frontend/package.json
  - livekit-client dependency.

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

    User->>UI: Enable Dictation or TTS
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
    User->>UI: Review/edit and submit
~~~

Noise and low-amplitude audio are filtered before final transcription.
Whisper output is also filtered for silence probability, compression-ratio
hallucinations, low-confidence segments, and known static boilerplate.

### 4.3 TTS commentary

~~~mermaid
sequenceDiagram
    participant UI as DeepSpaceChatClient
    participant LK as LiveKit
    participant VA as voice-agent
    participant Provider as Configured chat provider
    participant TTS as Kokoro
    actor User

    UI->>UI: Detect completed assistant answer
    UI->>LK: Send test-tts text payload once
    LK->>VA: TTS request
    VA->>TTS: Synthesize spoken text
    TTS-->>VA: PCM samples
    VA->>LK: Publish agent audio track
    LK-->>User: Browser plays audio
~~~

The current frontend deliberately sends TTS after the assistant answer is
complete. It does not currently stream every internal tool event or private
reasoning step as spoken commentary.

### 4.4 Barge-in

When the user begins speaking while the agent is speaking, the voice agent
cancels the active TTS playback task and returns to listening state. This is
speech-playback interruption.

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
| Completed answer spoken aloud | Implemented |
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
9. A disposable user can connect, dictate, edit, and submit a message.
10. The same user can receive a completed answer over TTS.
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
  The current voice-agent provider helper contains a development-oriented user
  selection fallback and must not be treated as a production multi-tenant
  provider-resolution contract.
- Add a dedicated authenticated voice E2E suite to the maintained test tree if
  the release smoke is currently only an external/scripted check.
- Add an explicit voice-session cleanup and lifecycle metric policy.
- Define TURN and public-network deployment configuration for staging/VPS.
- Decide whether voice should ever submit commands automatically or remain
  review-before-send dictation.
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
