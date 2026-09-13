import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function WebResearchDocsPage() {
  return (
    <DocsShell
      title="Evidence-first Web Research"
      intro="DeepSpace research is backend-orchestrated: it searches, reads, ranks, verifies, and preserves evidence before a selected chat model writes an answer."
    >
      <DocsCards
        items={[
          {
            title: "Deterministic routing",
            body: "Explicit search, latest, verify, research, and find-online requests start backend research even if the selected model cannot call tools.",
          },
          {
            title: "Bounded retrieval",
            body: "Five focused queries collect up to 40 candidates, deduplicate URLs, rank diverse sources, and securely fetch up to six pages.",
          },
          {
            title: "Evidence over snippets",
            body: "Only fetched passages are supplied as verified research evidence. A failed fetch remains visibly search-snippet-only.",
          },
          {
            title: "Citations + quality",
            body: "Research answers use R-number citations. Each cited answer sentence is checked against the fetched passages; unsupported R-citations are removed and recorded in the research-quality audit.",
          },
        ]}
      />
      <DocsSection title="Safety and isolation">
        <p>
          All requests keep the existing tenant, user, provider, rate-limit, URL validation,
          redirect, size, and timeout boundaries. Browser rendering is disabled by default and must
          point to an explicitly deployed isolated renderer; it never accepts a renderer URL from a
          model or user.
        </p>
      </DocsSection>
      <DocsSection title="Independent-source verification">
        <p>
          Fetched passages from different domains are compared before sources are marked confirmed.
          Materially overlapping evidence can be marked confirmed; overlapping evidence with opposing
          polarity is marked conflicting. This is a conservative evidence signal, not a claim that a
          source is universally true.
        </p>
      </DocsSection>
      <DocsSection title="Known limits">
        <p>
          Paywalls, logins, anti-bot defenses, robots policies, and missing publication dates cannot
          be bypassed. AverQel labels unavailable pages and undated current-source results instead
          of presenting them as verified. The optional JavaScript browser must be deployed behind a
          separately administered network-egress policy before it is enabled; a standard Compose
          network alone is not sufficient isolation. AverQel supplies the <code>research-browser</code>
          Compose profile for local/staging use: it separates Chromium from application services and
          forces browser traffic through a private-range-blocking egress proxy. Set a unique renderer
          token, start that profile, run its smoke tests, then explicitly enable the browser setting.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
