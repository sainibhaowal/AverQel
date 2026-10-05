# 08. Public Landing Page and Product Areas

## 1. Purpose

The public landing page presents AverQel as a connected AI workspace while keeping each product
area's features and setup context together. It follows the product boundaries exposed by the
backend APIs and signed-in navigation; it does not combine unrelated capabilities into a single
directory or imply that deployment-dependent services are active.

## 2. Product section order

1. **Documents Hub** owns source-file intake, extraction and indexing status, inspection, versions,
   document organization, document-level automation, and sharing.
2. **Query** owns retrieval-first conversations, scoped source selection, streamed answers,
   citations, and Query history.
3. **Collections** owns explicit project membership, shared sources, and collection collaboration.
   The public page must retain the experimental beta status.
4. **DeepSpace** owns agent conversations and runs, Memory, its working Library, research and
   sandbox tools, artifacts and exports, and DeepSpace schedules. The DeepSpace Library contains
   work files and deliverables; it is separate from Documents Hub source files.
5. **AI Providers** owns model-provider configuration, model assignments, and provider health.
   Providers are shared runtime dependencies for Query and DeepSpace.
6. **MCP Servers** owns the approved marketplace, supported authorization flows, connection
   health, tool policies, action approvals, and supported DeepSpace or conversation scopes.
7. **Workspace controls** groups user-facing profile, plan and storage, privacy, support, and
   feedback information. Administration-only interfaces are not part of public landing content.

The hero may summarize the connected workspace and retain its existing runtime visualization.
Product details below it must remain grouped under the relevant product section. The call to action
and footer follow the product areas.

Landing cards summarize the main user-facing workflows; they are not a list of every API operation.
Detailed behavior, permission requirements, and deployment gates belong in the linked product guides.

## 3. Backend boundaries checked

The API routers are registered separately in `backend/app/main.py`:

- Documents Hub: source documents and document organization routers.
- Collections: separate collection membership, collaboration, and security routers.
- Query: `/queries` and Query chat/history routes.
- DeepSpace: `/deepspace/chats`, `/deepspace/library`, `/deepspace/artifacts`,
  `/deepspace/sandbox`, and `/deepspace/schedules`.
- AI Providers: `/providers`.
- MCP: `/mcp`.
- Support and feedback: their own user-facing system routes.

The page should preserve the distinction between Documents Hub's document smart collections and
the separate Collections collaboration area. It must also preserve the distinction between Query
conversation history and DeepSpace agent runs and Library files.

## 4. Frontend files

1. `frontend/app/page.tsx` composes the hero, product areas, call to action, and footer.
2. `frontend/app/components/marketing/ProductDomains.tsx` owns the ordered product sections and
   the feature cards within each section.
3. `frontend/app/components/marketing/HeroSection.tsx` and `MobileNav.tsx` link to those sections;
   the hero runtime visualization remains a separate, unchanged component.
4. `frontend/app/components/layout/Footer.tsx` links to the same product sections and public help,
   account, and policy guides.
5. Documentation links point to the corresponding guides under
   `frontend/app/documentation/`.

## 5. Truthfulness and release state

1. Supported document types and processing behavior are determined by the ingestion extractors and
   deployment configuration. Do not present remote apps or MCP servers as document formats.
2. Provider access depends on configured credentials, assignments, and service health.
3. MCP connections originate from approved catalog entries and remain subject to ownership,
   endpoint validation, tool policies, and action approval requirements. Do not promise arbitrary
   endpoint registration.
4. DeepSpace schedules require the configured worker and scheduler services for recurring
   execution. Sandbox and voice capabilities can have separate deployment requirements.
5. Collections retain their experimental beta label until release status changes.
6. Public landing content must not expose secrets, internal endpoints, private API routes, or
   administration-only interfaces.

## 6. Verification

The landing-page checks cover product-section order and ownership, key feature placement, relevant
links, and the continued separation of Documents Hub, Query, Collections, DeepSpace, providers, and
MCP. Local UI checks do not prove external provider credentials or deployment-dependent services
are live.

## 7. Notification polling note

The dashboard notification center polls the authenticated endpoint every 15 seconds. It prevents
overlapping requests and uses a 10-second request budget, so a transient browser or network stall
cannot keep a request pending for the full global 30-second API timeout. The backend endpoint remains
tenant-scoped and indexed; a timeout should still be investigated with the browser Network panel and
API logs rather than treated as a successful response.
