import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function VoiceDocsPage() {
  return (
    <DocsShell
      title="DeepSpace voice"
      intro="DeepSpace has a review-before-send dictation control and a voice conversation control that uses the chat you already have open. Voice requires the realtime service and browser microphone access."
    >
      <DocsCards
        items={[
          {
            title: "Dictate to composer",
            body: "Live speech appears as an editable draft in the composer. Pause and resume, or finish to keep the text for review. Dictation never sends the message for you and stops after ten minutes of active listening.",
          },
          {
            title: "Voice conversation",
            body: "Speech is sent as a turn to the currently selected DeepSpace chat. The same DeepSpace model and tools answer, and new visible sentences are spoken as they arrive. Select a built-in voice in Settings > Voice Studio for realtime conversation.",
          },
          {
            title: "Only new response text is spoken",
            body: "Voice does not read chat history, hidden reasoning, or raw tool results. A brief generic status can announce tool work without reading tool names, inputs, or results.",
          },
          {
            title: "Browser permissions",
            body: "Microphone access requires a secure browser context and explicit permission. You can revoke that permission in browser settings.",
          },
          {
            title: "Voice activity display",
            body: "The animated waveform sits beside the voice buttons in the composer. It shows green activity while listening, flowing colored lines while processing, and a moving blue-violet wave while speaking. Listening waves follow available microphone activity.",
          },
        ]}
      />
      <DocsSection title="How voice conversation works">
        <p>
          Voice conversation uses the existing DeepSpace request and response path. Speech is
          transcribed after a pause, then DeepSpace streams its answer and Pocket TTS speaks visible
          response segments through the same WebRTC session. Interim transcription is best effort,
          not guaranteed word-by-word output. Configure a built-in voice in Settings &gt; Voice
          Studio. Cloned voices are not currently available in realtime conversations. The first
          connection can take longer while speech models load. This keeps the answer in the selected
          chat instead of starting a second assistant conversation.
        </p>
        <p>
          Spoken output starts with complete visible sentences. Any unfinished sentence is flushed
          when a tool step starts or the turn ends. If no recent sentence was spoken, a brief
          generic status can announce tool work without reading tool names, inputs, or results. Code
          blocks are skipped. Speaking can be interrupted by speaking again; that stops queued audio
          while the DeepSpace task continues under its usual queue controls.
        </p>
        <p>
          The current setup is a speech-to-text, DeepSpace chat, and text-to-speech pipeline. It is
          not a single audio-native speech-to-speech model. The selected DeepSpace model remains the
          only model that answers your request or calls its tools.
        </p>
      </DocsSection>
      <DocsSection title="Dictation controls">
        <p>
          Choose Dictate to composer to start live transcription. Interim words update in place as
          recognition revises them; a finished phrase is committed once. Pause stops the microphone
          after asking the voice agent to finish the current phrase. Resume continues the same
          draft, and Finish closes the voice session while leaving the draft ready to edit and send.
          The ten-minute limit counts active listening time, not paused time.
        </p>
        <p>
          Dictation uses the configured local Faster-Whisper model. Recognition quality depends on
          the selected model, microphone placement, background noise, accent, and available CPU;
          review the transcript before sending.
        </p>
      </DocsSection>
      <DocsSection title="Voice preview timing">
        <p>
          Test Voice returns a complete audio preview after the server has generated the sample. It
          is not a live-streaming test. A server worker may need to load the speech model the first
          time it receives a preview request. When the player appears, use its play control if your
          browser does not start playback automatically.
        </p>
      </DocsSection>
      <DocsSection title="Deployment requirements">
        <p>
          Operators need to deploy and configure the realtime transport (such as LiveKit) and voice
          agent, provide secure HTTPS/WSS connectivity, and validate network routing including TURN
          where needed. The production Compose stack does not itself prove those external services
          are available.
        </p>
      </DocsSection>
      <DocsSection title="Privacy and availability">
        <p>
          Voice sends audio through the configured realtime service and agent. Review the privacy
          information for the deployment and any external voice provider before use. Local UI code
          or a simulated test does not establish physical-device, network, or hosted-production
          readiness.
        </p>
        <p>
          If DeepSpace cannot request a voice token or reach the voice service, it turns the voice
          controls back off and shows “Voice server unreachable.” Text chat remains available.
        </p>
        <p>
          Dictation is shown as active only after the browser enables the microphone and the voice
          agent confirms the mode. If the browser blocks microphone access, the controls reset and
          ask you to check permission and the selected input device. If dictation does not connect,
          check that the voice agent is running. If it connects but no words appear, check that the
          operating system and browser are receiving sound from the selected device.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
