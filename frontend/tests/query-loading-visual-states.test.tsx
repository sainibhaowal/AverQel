import { render, screen } from "@testing-library/react";

import StreamingTypingIndicator from "../app/dashboard/query/_components/StreamingTypingIndicator";

describe("query loading visual states", () => {
  it("renders searching, grounding, and answering states with helper text", () => {
    const { rerender } = render(<StreamingTypingIndicator phase="searching" />);
    expect(screen.getByText(/searching evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/scanning the workspace/i)).toBeInTheDocument();

    rerender(<StreamingTypingIndicator phase="grounding" />);
    expect(screen.getByText(/grounding answer/i)).toBeInTheDocument();
    expect(screen.getByText(/cross-checking evidence/i)).toBeInTheDocument();

    rerender(<StreamingTypingIndicator phase="answering" />);
    expect(screen.getByText(/streaming response/i)).toBeInTheDocument();
    expect(screen.getByText(/writing the response/i)).toBeInTheDocument();
  });
});
