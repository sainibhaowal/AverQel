import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DeepSpaceComposer from "../app/dashboard/deepspace/_components/DeepSpaceComposer";
import DeepSpaceVoicePresence from "../app/dashboard/deepspace/_components/DeepSpaceVoicePresence";

describe("DeepSpaceVoicePresence", () => {
  it("does not render when voice is inactive", () => {
    render(<DeepSpaceVoicePresence state="idle" />);

    expect(screen.queryByTestId("deepspace-voice-presence")).not.toBeInTheDocument();
  });

  it.each([
    ["listening", "Voice mode is listening"],
    ["thinking", "Voice mode is working"],
    ["speaking", "Voice mode is speaking"],
  ] as const)("renders the %s state beside the composer voice controls", (state, label) => {
    render(
      <DeepSpaceComposer
        query=""
        isStreaming={false}
        voiceState={state}
        voiceActivityLevel={0.72}
        onQueryChange={() => {}}
        onSubmit={() => {}}
        onStop={() => {}}
      />,
    );

    const voiceControls = screen.getByTestId("deepspace-voice-controls");
    expect(within(voiceControls).getByRole("status", { name: label })).toHaveAttribute(
      "data-voice-state",
      state,
    );
    expect(within(voiceControls).getByTestId("deepspace-voice-waveform")).toHaveAttribute(
      "data-voice-level",
      "0.72",
    );

    if (state === "listening") {
      expect(within(voiceControls).getAllByTestId("deepspace-voice-wave-bar")).toHaveLength(11);
    } else {
      const traces = within(voiceControls).getAllByTestId("deepspace-voice-wave-trace");
      expect(traces).toHaveLength(2);
      expect(traces[0]).toHaveClass("deepspace-voice-wave-trace");
      expect(traces[1]).toHaveClass("deepspace-voice-wave-trace--second");
      expect(traces[0]).toHaveAttribute("stroke-dasharray", "0.14 0.08");
    }
  });

  it("clamps malformed audio activity before exposing it to the waveform", () => {
    render(<DeepSpaceVoicePresence state="listening" activityLevel={4} />);

    expect(screen.getByTestId("deepspace-voice-waveform")).toHaveAttribute(
      "data-voice-level",
      "1.00",
    );
  });

  it("offers pause, resume, and finish controls without sending dictated text", async () => {
    const onDictationPause = vi.fn();
    const onDictationFinish = vi.fn();
    const onSubmit = vi.fn();
    const { rerender } = render(
      <DeepSpaceComposer
        query="Draft from speech"
        isStreaming={false}
        sttActive
        dictationSessionOpen
        dictationElapsedSeconds={72}
        onDictationPause={onDictationPause}
        onDictationFinish={onDictationFinish}
        onQueryChange={() => {}}
        onSubmit={onSubmit}
        onStop={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Pause dictation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finish dictation" })).toBeInTheDocument();
    expect(screen.getByTestId("dictation-elapsed")).toHaveTextContent("1:12 / 10:00");
    fireEvent.click(screen.getByRole("button", { name: "Pause dictation" }));

    const onResume = vi.fn();
    rerender(
      <DeepSpaceComposer
        query="Draft from speech"
        isStreaming={false}
        dictationSessionOpen
        onSttToggle={onResume}
        onDictationFinish={onDictationFinish}
        onQueryChange={() => {}}
        onSubmit={onSubmit}
        onStop={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Resume dictation" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause dictation" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resume dictation" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish dictation" }));
    expect(onDictationPause).toHaveBeenCalledTimes(1);
    expect(onResume).toHaveBeenCalledTimes(1);
    expect(onDictationFinish).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
