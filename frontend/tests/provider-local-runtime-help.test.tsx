import { render, screen } from "@testing-library/react";

import ProviderLocalRuntimeHelp from "../app/components/providers/ProviderLocalRuntimeHelp";

describe("provider local runtime help", () => {
  it("renders ollama and lm studio setup help", () => {
    const { rerender } = render(<ProviderLocalRuntimeHelp providerType="ollama" />);
    expect(screen.getByText(/ollama local runtime/i)).toBeInTheDocument();
    expect(screen.getByText(/127.0.0.1:11434/i)).toBeInTheDocument();
    expect(screen.getByText(/official api/i)).toBeInTheDocument();
    expect(screen.getByText(/separate chat and embedding defaults/i)).toBeInTheDocument();

    rerender(<ProviderLocalRuntimeHelp providerType="lmstudio" />);
    expect(screen.getByText(/lm studio local runtime/i)).toBeInTheDocument();
    expect(screen.getByText(/127.0.0.1:1234\/v1/i)).toBeInTheDocument();
    expect(screen.getByText(/host\.docker\.internal:1234\/v1/i)).toBeInTheDocument();
    expect(screen.getByText(/remote hosted averqel/i)).toBeInTheDocument();
    expect(
      screen.getByText(/does not install or download lm studio models directly/i),
    ).toBeInTheDocument();
  });
});
