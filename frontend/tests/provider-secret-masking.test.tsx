import { render, screen } from "@testing-library/react";

import ProviderSecretField from "../app/components/providers/ProviderSecretField";

describe("provider secret masking", () => {
  it("shows only masked saved secret summaries", () => {
    render(<ProviderSecretField value="" onChange={() => {}} maskedSummary="sk-...abcd" />);

    expect(screen.getByDisplayValue("")).toBeInTheDocument();
    expect(screen.getByText(/saved secret: sk-\.\.\.abcd/i)).toBeInTheDocument();
    expect(screen.queryByDisplayValue("sk-live-raw-secret")).not.toBeInTheDocument();
  });
});
