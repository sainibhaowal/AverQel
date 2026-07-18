type HistoryMessage = {
  id: string;
  role: "user" | "assistant";
};

type Fetcher = (input: string, init?: RequestInit) => Promise<Response>;

interface ResolveLatestEditableMessageIdArgs {
  fetcher: Fetcher;
  endpointBase: string;
  conversationId: string;
  fallbackMessageId: string;
}

export async function resolveLatestEditableMessageId({
  fetcher,
  endpointBase,
  conversationId,
  fallbackMessageId,
}: ResolveLatestEditableMessageIdArgs): Promise<string> {
  try {
    const response = (await fetcher(`${endpointBase}/${conversationId}/messages`)) as Response;
    if (!response.ok) {
      return fallbackMessageId;
    }

    const payload = (await response.json()) as { messages?: HistoryMessage[] };
    const latestUserMessage = [...(payload.messages ?? [])]
      .reverse()
      .find((message) => message.role === "user" && typeof message.id === "string");

    return latestUserMessage?.id ?? fallbackMessageId;
  } catch {
    return fallbackMessageId;
  }
}
