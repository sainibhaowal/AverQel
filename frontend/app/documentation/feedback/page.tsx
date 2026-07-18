import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function FeedbackDocsPage() {
  return (
    <DocsShell
      title="Share Feedback"
      intro="Submit suggestions, evaluate system usability, and propose feature requirements directly to the AverQel development team."
    >
      <DocsCards
        items={[
          {
            title: "Feature Requests",
            body: "Submit proposals for new connectors, custom E2EE algorithms, advanced visualizers, or specific integrations.",
          },
          {
            title: "Usability Evaluations",
            body: "Report design suggestions, performance bottlenecks, or navigation difficulties to help optimize interface experiences.",
          },
          {
            title: "Roadmap Voting",
            body: "Upvote items in the active product development queue to prioritize what the engineering team tackles next.",
          },
          {
            title: "Community Forum",
            body: "Engage with other AverQel operators to share setups, custom MCP connectors, and background agent scripts.",
          },
        ]}
      />

      <DocsSection title="Feedback Collection Policy">
        <p>
          Feedback submissions are voluntary and help shape the platform. We collect feature requirements, system versions, and anonymized usability logs to address bugs and direct resources toward high-demand integrations.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
