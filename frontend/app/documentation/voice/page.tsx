import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function VoiceDocsPage() {
  return (
    <DocsShell
      title="DeepSpace voice"
      intro="Voice is an optional DeepSpace input and output path. Its controls work only when the deployment has the realtime service and voice agent configured and the browser grants microphone access."
    >
      <DocsCards
        items={[
          {
            title: "Speech input",
            body: "Use the microphone control to dictate into the DeepSpace composer during a connected voice session.",
          },
          {
            title: "Spoken response",
            body: "Text-to-speech can speak a completed assistant response when the voice session and agent support it; it is not a promise of continuous spoken progress updates.",
          },
          {
            title: "Text remains available",
            body: "DeepSpace text chat does not require voice. If the realtime service is unavailable, voice may be disabled while text workflows remain separate.",
          },
          {
            title: "Browser permissions",
            body: "Microphone access requires a secure browser context and explicit permission. You can revoke that permission in browser settings.",
          },
        ]}
      />
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
