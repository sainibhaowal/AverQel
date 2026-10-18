import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DeepSpaceComposer from "../app/dashboard/deepspace/_components/DeepSpaceComposer";

describe("DeepSpaceComposer active-turn controls", () => {
  it("grows the message field up to five rows, then scrolls longer drafts inside it", () => {
    const renderComposer = (query: string) => (
      <DeepSpaceComposer
        query={query}
        isStreaming={false}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />
    );
    const { rerender } = render(renderComposer(""));
    const textarea = screen.getByPlaceholderText("Message DeepSpace...") as HTMLTextAreaElement;
    let measuredScrollHeight = 72;
    Object.defineProperty(textarea, "scrollHeight", {
      configurable: true,
      get: () => measuredScrollHeight,
    });

    rerender(renderComposer("A short prompt"));
    const compactHeight = Number.parseFloat(textarea.style.height);
    expect(compactHeight).toBeGreaterThan(0);
    expect(textarea.style.overflowY).toBe("hidden");

    measuredScrollHeight = 500;
    rerender(renderComposer("A much longer prompt that needs more room"));
    const expandedHeight = Number.parseFloat(textarea.style.height);
    expect(textarea).toHaveAttribute("rows", "2");
    expect(textarea).toHaveClass("max-h-[8.5rem]");
    expect(expandedHeight).toBeGreaterThan(compactHeight);
    expect(expandedHeight).toBeLessThanOrEqual(136);
    expect(textarea.style.overflowY).toBe("auto");
  });

  it("hides Steer and Stop without an active assistant while keeping queue sending available", () => {
    render(
      <DeepSpaceComposer
        query="A new message"
        isStreaming
        showActiveResponseControls={false}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        onSteer={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Steer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop response" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Queue message" })).toBeInTheDocument();
  });

  it("shows the live output estimate and generation rate during a stream", () => {
    render(
      <DeepSpaceComposer
        query=""
        isStreaming
        contextUsedTokens={4516}
        contextLimit={1_048_576}
        requestInputTokens={4516}
        requestOutputTokens={12}
        liveTokensPerSecond={7.5}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    expect(screen.getByText(/4,516 model in · 12 model out ·/)).toBeInTheDocument();
    expect(screen.getByText(/~7\.5 tok\/s/)).toBeInTheDocument();
  });

  it("labels turn estimates separately from latest provider-round usage", () => {
    render(
      <DeepSpaceComposer
        query=""
        isStreaming={false}
        contextUsedTokens={8_046}
        contextLimit={1_048_576}
        requestInputTokens={38_952}
        requestOutputTokens={1_908}
        requestInputTokensSource="serialized_request_estimate"
        requestOutputTokensSource="serialized_response_estimate"
        providerUsage={{
          input_tokens: 7_324,
          output_tokens: 901,
          cached_input_tokens: 7_168,
          cache_write_input_tokens: 0,
          usage_source: "provider",
        }}
        providerUsageScope="latest_reported_round"
        providerUsageRoundCount={5}
        providerTurnUsage={{
          input_tokens: 38_952,
          output_tokens: 1_908,
          cached_input_tokens: 35_840,
          cache_write_input_tokens: 0,
          usage_source: "provider",
        }}
        promptCacheMode="google_implicit"
        promptCacheStatus="native_requested"
        promptCacheEligible
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Show context usage details" }));
    const dialog = screen.getByRole("dialog", { name: "Context usage details" });
    expect(dialog).toHaveTextContent("Latest round context estimate");
    expect(dialog).toHaveTextContent("Turn input estimate (all rounds)");
    expect(dialog).toHaveTextContent("Provider usage (latest reported model round)");
    expect(dialog).toHaveTextContent("input 7,324 · output 901 · cache read 7,168");
    expect(dialog).toHaveTextContent("Provider turn total (5 reported rounds): input 38,952");
    expect(dialog).toHaveTextContent("google_implicit reported by provider");
  });

  it("shows an opaque attachment tooltip above the animated composer border", () => {
    render(
      <DeepSpaceComposer
        conversationId="conversation-1"
        query=""
        isStreaming={false}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    const attachmentButton = screen.getByRole("button", { name: "Attach files from your device" });
    fireEvent.mouseEnter(attachmentButton);

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent("Attach files or paste a screenshot");
    expect(tooltip).toHaveClass("averqel-tooltip-surface", "fixed", "z-[10000]");
    expect(tooltip.parentElement).toBe(document.body);
    expect(attachmentButton).toHaveAttribute("aria-describedby", "deepspace-attach-files-tooltip");

    fireEvent.mouseLeave(attachmentButton);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("keeps the reasoning menu opaque and above the animated composer border", () => {
    render(
      <DeepSpaceComposer
        query=""
        isStreaming={false}
        modelName="gemini-3-pro"
        availableModels={[
          {
            providerId: "google",
            providerName: "Google",
            modelName: "gemini-3-pro",
            displayName: "Gemini 3 Pro",
            reasoningCapabilitiesKnown: true,
            supportedReasoningEfforts: ["medium"],
          },
        ]}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Choose reasoning effort" }));

    const mediumOption = screen.getByRole("button", { name: "Medium" });
    const menu = mediumOption.parentElement;
    expect(menu).toHaveClass(
      "deepspace-reasoning-menu",
      "isolate",
      "bg-[#f4fbf7]",
      "dark:bg-[#101612]",
    );
    expect(menu?.closest('[class*="z-[80]"]')).not.toBeNull();
  });

  it("keeps the draft editable and exposes queue, steer, stop, and removal actions", () => {
    const onSubmit = vi.fn();
    const onStop = vi.fn();
    const onSteer = vi.fn();
    const onCancelQueuedTurn = vi.fn();

    render(
      <DeepSpaceComposer
        query="Use the second file instead"
        isStreaming
        onQueryChange={vi.fn()}
        onSubmit={onSubmit}
        onStop={onStop}
        onSteer={onSteer}
        queuedTurns={[
          {
            clientRequestId: "queued-1",
            prompt: "Summarize the next document",
            status: "queued",
          },
        ]}
        onCancelQueuedTurn={onCancelQueuedTurn}
      />,
    );

    expect(screen.getByPlaceholderText("Message DeepSpace...")).not.toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Queue message" }));
    fireEvent.click(screen.getByRole("button", { name: "Stop response" }));
    fireEvent.click(screen.getByRole("button", { name: "Steer" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove queued message 1" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onStop).toHaveBeenCalledOnce();
    expect(onSteer).toHaveBeenCalledOnce();
    expect(onCancelQueuedTurn).toHaveBeenCalledWith("queued-1");
  });

  it("opens a queued prompt in edit mode and saves it without submitting a new turn", async () => {
    const onSubmit = vi.fn();
    const onSaveQueueEdit = vi.fn(async () => true);
    const onCancelQueueEdit = vi.fn();

    render(
      <DeepSpaceComposer
        query="Revised queued prompt"
        isStreaming
        editingQueuedTurnId="queued-1"
        onQueryChange={vi.fn()}
        onSubmit={onSubmit}
        onSaveQueueEdit={onSaveQueueEdit}
        onCancelQueueEdit={onCancelQueueEdit}
        onStop={vi.fn()}
        queuedTurns={[
          {
            clientRequestId: "queued-1",
            prompt: "Original queued prompt",
            status: "queued",
          },
        ]}
      />,
    );

    expect(screen.getByPlaceholderText("Edit queued prompt…")).toHaveValue("Revised queued prompt");
    expect(screen.getByText(/saving keeps its current place in line/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save queued prompt" }));
    expect(onSaveQueueEdit).toHaveBeenCalledWith("queued-1", "Revised queued prompt");
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    expect(onCancelQueueEdit).toHaveBeenCalledOnce();
  });

  it("offers edit only for still-pending queue rows", () => {
    const onEditQueuedTurn = vi.fn();

    render(
      <DeepSpaceComposer
        query=""
        isStreaming={false}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        onEditQueuedTurn={onEditQueuedTurn}
        queuedTurns={[
          { clientRequestId: "queued-1", prompt: "Pending prompt", status: "queued" },
          { clientRequestId: "failed-1", prompt: "Failed prompt", status: "failed" },
          { clientRequestId: "waiting-1", prompt: "Running prompt", status: "running" },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit queued message 1" }));
    expect(onEditQueuedTurn).toHaveBeenCalledWith("queued-1");
    expect(screen.queryByRole("button", { name: "Edit queued message 2" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit queued message 3" })).not.toBeInTheDocument();
  });

  it("filters models by display name, model id, provider, and quantization", () => {
    const onModelSelect = vi.fn();

    render(
      <DeepSpaceComposer
        query=""
        isStreaming={false}
        modelName="deepseek-v4-pro"
        availableModels={[
          {
            providerId: "lmstudio",
            modelName: "deepseek-v4-pro",
            displayName: "DeepSeek V4 Pro",
            quantization: "Q4_K_M",
          },
          {
            providerId: "openai",
            modelName: "gpt-5-mini",
            displayName: "GPT-5 Mini",
          },
        ]}
        onModelSelect={onModelSelect}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /deepseek-v4-pro/i }));
    const modelSearch = screen.getByRole("searchbox", { name: "Search models" });
    expect(modelSearch).toHaveClass("rounded-md");
    expect(modelSearch).not.toHaveClass("rounded-full");
    fireEvent.change(modelSearch, {
      target: { value: "q4_k_m" },
    });

    expect(screen.getByRole("button", { name: /deepseek v4 pro/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /gpt-5 mini/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /deepseek v4 pro/i }));
    expect(onModelSelect).toHaveBeenCalledWith("lmstudio", "deepseek-v4-pro");
  });

  it("groups providers and models alphabetically and keeps one provider expanded", () => {
    const onModelSelect = vi.fn();

    render(
      <DeepSpaceComposer
        query=""
        isStreaming={false}
        availableModels={[
          {
            providerId: "openai-id",
            providerName: "OpenAI",
            providerType: "openai",
            modelName: "gpt-zeta",
            displayName: "GPT Zeta",
          },
          {
            providerId: "lmstudio-id",
            providerName: "LM Studio",
            providerType: "lmstudio",
            modelName: "local-zeta",
            displayName: "Zeta Local",
          },
          {
            providerId: "anthropic-id",
            providerName: "Anthropic",
            providerType: "anthropic",
            modelName: "claude-sonnet",
            displayName: "Claude Sonnet",
          },
          {
            providerId: "lmstudio-id",
            providerName: "LM Studio",
            providerType: "lmstudio",
            modelName: "local-alpha",
            displayName: "Alpha Local",
          },
        ]}
        onModelSelect={onModelSelect}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /select model/i }));
    const modelMenu = document.querySelector(".deepspace-model-menu");
    expect(modelMenu).toHaveClass(
      "h-[min(22rem,calc(100dvh-2rem))]",
      "w-[min(31rem,calc(100vw-2rem))]",
    );
    const fixedMenuClasses = modelMenu?.className;

    const providerHeadings = screen
      .getAllByRole("button")
      .filter((button) => button.classList.contains("deepspace-model-provider-heading"));
    expect(
      providerHeadings.map(
        (button) => button.querySelector(".deepspace-model-provider-name")?.textContent,
      ),
    ).toEqual(["Anthropic", "LM Studio", "OpenAI"]);
    expect(screen.getByRole("button", { name: /anthropic/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("button", { name: /lm studio/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByRole("button", { name: /claude sonnet/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /lm studio/i }));
    expect(screen.getByRole("button", { name: /anthropic/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByRole("button", { name: /lm studio/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(modelMenu?.className).toBe(fixedMenuClasses);
    const lmStudioModels = screen.getByRole("group", { name: "LM Studio models" });
    expect(
      within(lmStudioModels)
        .getAllByRole("button")
        .map((button) => button.textContent?.trim()),
    ).toEqual(["Alpha Local", "Zeta Local"]);

    fireEvent.change(screen.getByRole("searchbox", { name: "Search models" }), {
      target: { value: "openai" },
    });
    expect(screen.getByRole("button", { name: /openai/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: /gpt zeta/i }));
    expect(onModelSelect).toHaveBeenCalledWith("openai-id", "gpt-zeta");
  });

  it("keeps a failed turn visible with separate queue-resume and prompt-retry actions", () => {
    const onResumeQueue = vi.fn();
    const onRetryFailedTurn = vi.fn();

    render(
      <DeepSpaceComposer
        query=""
        isStreaming={false}
        queuePaused
        queueFailedRequestId="failed-1"
        queuePauseReason="web_search failed: provider unavailable"
        queuedTurns={[
          {
            clientRequestId: "failed-1",
            prompt: "Search the report",
            status: "failed",
            error: "web_search failed: provider unavailable",
          },
        ]}
        onResumeQueue={onResumeQueue}
        onRetryFailedTurn={onRetryFailedTurn}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    expect(screen.getByText("Queue paused")).toBeInTheDocument();
    expect(screen.getAllByText("web_search failed: provider unavailable")).toHaveLength(2);
    for (const name of [
      "Attach files from your device",
      "Take a photo",
      "Attach an existing Library file",
    ]) {
      const attachmentAction = screen.getByRole("button", { name });
      expect(attachmentAction).toHaveAttribute("aria-label", name);
      expect(attachmentAction).not.toHaveAttribute("title");
      expect(attachmentAction).not.toHaveAttribute("data-tooltip");
    }
    fireEvent.click(screen.getByRole("button", { name: "Continue queued prompts" }));
    const retryButton = screen.getByRole("button", { name: "Retry prompt" });
    expect(retryButton).toHaveClass("text-cyan-800", "dark:text-cyan-200");
    expect(screen.getAllByText("web_search failed: provider unavailable")[1]).toHaveClass(
      "text-red-700/80",
    );
    fireEvent.click(retryButton);
    expect(onResumeQueue).toHaveBeenCalledOnce();
    expect(onRetryFailedTurn).toHaveBeenCalledWith("failed-1");
  });

  it("labels queued regeneration and prevents editing its source prompt", () => {
    render(
      <DeepSpaceComposer
        query=""
        isStreaming
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        queuedTurns={[
          {
            clientRequestId: "regenerate-1",
            regenerateMessageId: "assistant-1",
            prompt: "Regenerate the saved answer",
            status: "queued",
          },
        ]}
      />,
    );

    expect(screen.getByText("Regenerate reply: Regenerate the saved answer")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit queued message 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove queued message 1" })).toBeInTheDocument();
  });
});
