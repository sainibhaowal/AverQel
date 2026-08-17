import { fetchWithAuth } from "@/lib/api";

const ACTIVE_CONVERSATION_KEY = "averqel_deepspace_active_conversation";

interface SaveDocumentContentOptions {
  title: string;
  contentHtml: string;
}

interface ConversationResponse {
  id: string;
}

/**
 * Append document content to the user's active DeepSpace note. If the active
 * note is unavailable (for example, a stale browser tab), create a new note.
 * The server validates tenant and user ownership for both paths.
 */
export async function saveDocumentContentToDeepSpace({
  title,
  contentHtml,
}: SaveDocumentContentOptions): Promise<ConversationResponse> {
  if (!contentHtml.trim()) {
    throw new Error("There is no document content to save.");
  }

  const activeConversationId = window.localStorage.getItem(ACTIVE_CONVERSATION_KEY);
  if (activeConversationId) {
    const appendResponse = (await fetchWithAuth(
      `/deepspace/chats/${encodeURIComponent(activeConversationId)}/append-content`,
      {
        method: "POST",
        body: JSON.stringify({ content_html: contentHtml, title }),
      },
    )) as Response;

    if (appendResponse.ok) {
      return (await appendResponse.json()) as ConversationResponse;
    }

    // A deleted note or a note from an older session should not make the
    // document action fail forever. Other errors (auth, validation, server)
    // must be surfaced and must not silently create a second note.
    if (appendResponse.status !== 404) {
      throw new Error("The active DeepSpace note could not be updated.");
    }
    window.localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
  }

  const createResponse = (await fetchWithAuth("/deepspace/chats", {
    method: "POST",
    body: JSON.stringify({ title, content_html: contentHtml }),
  })) as Response;
  if (!createResponse.ok) {
    throw new Error("A DeepSpace note could not be created.");
  }

  const created = (await createResponse.json()) as ConversationResponse;
  if (created.id) {
    window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, created.id);
  }
  return created;
}
