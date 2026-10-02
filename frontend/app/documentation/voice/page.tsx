import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function VoiceDocsPage() {
  return (
    <DocsShell
      title="Voice & Realtime"
      intro="DeepSpace can listen through speech-to-text dictation and speak through text-to-speech commentary over a private realtime session. Voice is deployment-gated: it needs the realtime service and a granted microphone."
    >
      <DocsCards
        items={[
          {
            title: "Voice Dictation (STT)",
            body: "Dictate into the DeepSpace composer instead of typing. Microphone audio stays inside your tenant-scoped realtime session.",
          },
          {
            title: "Voice Commentary (TTS)",
            body: "Hear spoken commentary on agent progress and answers through a dedicated agent audio track.",
          },
          {
            title: "Same Workspace",
            body: "Voice drives the same durable chat: queued turns, approvals, memory, notes, and saved history keep working while you talk.",
          },
          {
            title: "Private Session",
            body: "The browser connects over the same HTTPS origin and a short-lived token bound to your user identity.",
          },
        ]}
      />

      <DocsSection title="What you need">
        <ul className="list-disc space-y-2 pl-6">
          <li>a deployment with the realtime (LiveKit) service enabled</li>
          <li>HTTPS origin — browsers only grant microphone access in secure contexts</li>
          <li>microphone permission granted to the site in the browser prompt</li>
        </ul>
      </DocsSection>

      <DocsSection title="Deployment status">
        <p>
          Voice transport and agent wiring pass local checks with a simulated microphone. A physical
          microphone and device-permission check, plus external staging proof, remain deployment
          gates — voice is labelled “Deployment gated” until those are recorded.
        </p>
      </DocsSection>

      <DocsSection title="What users notice">
        <ul className="list-disc space-y-2 pl-6">
          <li>microphone and speaker buttons in the DeepSpace composer</li>
          <li>speech-to-text becomes active once the realtime session connects</li>
          <li>spoken commentary arrives as agent audio without changing the saved transcript</li>
          <li>if the realtime service is disabled, voice controls stay unavailable — text chat is unaffected</li>
        </ul>
      </DocsSection>
    </DocsShell>
  );
}
