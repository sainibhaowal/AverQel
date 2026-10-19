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
            body: "Speech is transcribed into the composer. Review or edit the text, then send it when you are ready.",
          },
          {
            title: "Voice conversation",
            body: "Speech is sent as a turn to the currently selected DeepSpace chat. The same DeepSpace model and tools answer, and new visible sentences are spoken as they arrive.",
          },
          {
            title: "Only new response text is spoken",
            body: "Voice does not read chat history, hidden reasoning, or raw tool results. A brief generic status can announce tool work without reading tool names, inputs, or results.",
          },
          {
            title: "Browser permissions",
            body: "Microphone access requires a secure browser context and explicit permission. You can revoke that permission in browser settings.",
          },
        ]}
      />
      <DocsSection title="How voice conversation works">
        <p>
          Voice conversation uses the existing DeepSpace request and response path. Faster-Whisper
          transcribes your speech, the selected DeepSpace chat model handles your request and
          connected tools, and Kokoro speaks short visible response segments through the same voice
          session. This keeps the answer in the selected chat instead of starting a second assistant
          conversation.
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
      </DocsSection>
    </DocsShell>
  );
}
