export interface DeepSpaceLocalNoteDraft {
  version: 1;
  conversationId: string;
  contentHtml: string;
  title: string;
  baseUpdatedAt: string;
  updatedAt: number;
}

type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const NOTE_DRAFT_STORAGE_PREFIX = "averqel_deepspace_note_draft:";

export function noteDraftStorageKey(conversationId: string): string {
  return `${NOTE_DRAFT_STORAGE_PREFIX}${conversationId}`;
}

export function readDeepSpaceNoteDraft(
  storage: DraftStorage,
  conversationId: string,
): DeepSpaceLocalNoteDraft | null {
  try {
    const value = storage.getItem(noteDraftStorageKey(conversationId));
    if (!value) return null;
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== "object") return null;
    const draft = parsed as Partial<DeepSpaceLocalNoteDraft>;
    if (
      draft.version !== 1 ||
      draft.conversationId !== conversationId ||
      typeof draft.contentHtml !== "string" ||
      typeof draft.title !== "string" ||
      typeof draft.baseUpdatedAt !== "string" ||
      typeof draft.updatedAt !== "number"
    ) {
      return null;
    }
    return draft as DeepSpaceLocalNoteDraft;
  } catch {
    return null;
  }
}

export function writeDeepSpaceNoteDraft(
  storage: DraftStorage,
  draft: DeepSpaceLocalNoteDraft,
): boolean {
  try {
    storage.setItem(noteDraftStorageKey(draft.conversationId), JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

export function clearDeepSpaceNoteDraft(storage: DraftStorage, conversationId: string): void {
  try {
    storage.removeItem(noteDraftStorageKey(conversationId));
  } catch {
    // Storage may be unavailable in private browsing or under a restrictive policy.
  }
}
