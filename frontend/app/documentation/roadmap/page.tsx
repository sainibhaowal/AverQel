import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function RoadmapPage() {
  return (
    <DocsShell
      title="Release notes & product direction"
      intro="Use published releases and dated release notes for confirmed changes. This page does not promise delivery dates or represent an interactive public roadmap."
    >
      <DocsSection title="Where to find confirmed changes">
        <p>
          Released versions and their published notes are the record of changes that have shipped.
          Repository documentation can describe code present in a branch, while hosted availability
          depends on the deployment that has actually been released.
        </p>
        <p>
          Suggested improvements can be submitted through Share Feedback. A Planned status means a
          submission is under consideration; it is not a committed release date. This product page
          does not provide roadmap voting or a community forum.
        </p>
      </DocsSection>
      <DocsSection title="How priorities are handled">
        <p>
          Product direction may change as reliability, security, user needs, and deployment
          readiness are reviewed. A feature described in source or a development note is not
          necessarily enabled in production. Check the release version, rollout notes, and
          deployment-specific status before relying on it.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
