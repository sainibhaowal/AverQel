import { describe, expect, it } from "vitest";

import { buildMarketplaceQuery } from "../app/dashboard/mcp/page";

describe("buildMarketplaceQuery", () => {
  it("omits empty filters so the backend does not reject the request", () => {
    expect(
      buildMarketplaceQuery({
        q: "",
        category: "",
        transport: "",
        official: null,
        verified: null,
        page: 1,
      }),
    ).toBe("/mcp/marketplace?page=1");
  });

  it("includes only the active filters", () => {
    expect(
      buildMarketplaceQuery({
        q: "a search",
        category: "",
        transport: "streamable_http",
        official: true,
        verified: true,
        page: 3,
      }),
    ).toBe(
      "/mcp/marketplace?q=a+search&transport=streamable_http&official=true&verified=true&page=3",
    );
  });

  it("serializes dynamic auth, trust, and sort filters", () => {
    expect(buildMarketplaceQuery({
      q: "",
      category: "Productivity",
      transport: "streamable_http",
      official: null,
      verified: null,
      authType: "oauth",
      trustStatus: "approved",
      sort: "popular",
      page: 2,
    })).toBe("/mcp/marketplace?category=Productivity&transport=streamable_http&auth_type=oauth&trust_status=approved&sort=popular&page=2");
  });
});
