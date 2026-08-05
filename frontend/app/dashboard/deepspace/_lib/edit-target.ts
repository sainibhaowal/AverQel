export async function resolveLatestEditableMessageId({
  fetcher,
  endpointBase,
  conversationId,
  fallbackMessageId,
}: {
  fetcher: (input: string, init?: RequestInit) => Promise<Response>;
  endpointBase: string;
  conversationId: string;
  fallbackMessageId: string;
}): Promise<string> {
  try {
    const response = await fetcher(`${endpointBase}/${conversationId}/messages`);
    if (!response.ok) return fallbackMessageId;
    const payload = (await response.json()) as { messages?: Array<{ id: string; role: string }> };
    const messages = payload.messages ?? [];
    for (let index = messages.length - 1; index >= 1; index -= 1) {
      if (messages[index - 1]?.role === "user" && messages[index]?.role === "assistant")
        return messages[index - 1]!.id;
    }
  } catch {
    return fallbackMessageId;
  }
  return fallbackMessageId;
}
