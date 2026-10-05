import { describe, expect, it } from "vitest";
import { docsNavGroups } from "../app/documentation/_components/docsNav";

describe("public documentation navigation", () => {
  it("groups every product guide under its matching product area", () => {
    const links = docsNavGroups.flatMap((group) =>
      group.items.map((item) => ({ group: group.group, title: item.title, href: item.href })),
    );
    const find = (title: string) => links.find((link) => link.title === title);

    expect(find("Documents Hub")?.group).toBe("Documents Hub");
    expect(find("Organization & collaboration")?.group).toBe("Documents Hub");
    expect(find("Grounded queries")?.group).toBe("Query");
    expect(find("DeepSpace Library")?.group).toBe("DeepSpace");
    expect(find("Notes & editor")?.group).toBe("DeepSpace");
    expect(find("Web research")?.group).toBe("DeepSpace");
    expect(find("Sandbox & data analysis")?.group).toBe("DeepSpace");
    expect(find("Collections")?.group).toBe("Collections & sharing");
  });

  it("does not expose duplicate routes or a public admin handbook link", () => {
    const hrefs = docsNavGroups.flatMap((group) => group.items.map((item) => item.href));
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(hrefs).not.toContain("/documentation/admin");
  });
});
