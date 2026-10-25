import { describe, expect, it } from "vitest";

import {
  appendClientOwnedConversationContent,
  applyClientOwnedConversationUpdate,
} from "../lib/clientOwnedStorage";

const conversation = {
  id: "note-1",
  user_id: "user-1",
  kind: "deepspace",
  title: "Untitled Note",
  content_html: "<p>Existing note.</p>",
  created_at: "2026-10-23T12:00:00.000Z",
  updated_at: "2026-10-23T12:00:00.000Z",
};

describe("client-owned DeepSpace note writes", () => {
  it("updates only a note owned by the authenticated storage user", () => {
    const updated = applyClientOwnedConversationUpdate(
      conversation,
      {
        user_id: "user-1",
        kind: "deepspace",
        title: "Research plan",
        content_html: "<p>Saved note.</p>",
      },
      "2026-10-23T12:01:00.000Z",
    );

    expect(updated).toMatchObject({
      id: "note-1",
      title: "Research plan",
      content_html: "<p>Saved note.</p>",
      updated_at: "2026-10-23T12:01:00.000Z",
    });
    expect(conversation.content_html).toBe("<p>Existing note.</p>");
    expect(
      applyClientOwnedConversationUpdate(conversation, {
        user_id: "another-user",
        kind: "deepspace",
        content_html: "<p>Not authorized</p>",
      }),
    ).toBeNull();
  });

  it("appends generated or imported content without replacing the saved note", () => {
    const updated = appendClientOwnedConversationContent(
      conversation,
      {
        user_id: "user-1",
        kind: "deepspace",
        title: "Imported document",
        content_html: "<p>New selection.</p>",
      },
      "2026-10-23T12:02:00.000Z",
    );

    expect(updated).toMatchObject({
      title: "Imported document",
      content_html:
        '<p>Existing note.</p><hr data-averqel-document-separator="true" /><p>New selection.</p>',
      updated_at: "2026-10-23T12:02:00.000Z",
    });
    expect(
      appendClientOwnedConversationContent(conversation, {
        user_id: "user-1",
        kind: "query",
        content_html: "<p>Wrong conversation kind</p>",
      }),
    ).toBeNull();
  });

  it("restores a confirmed legacy copy before appending to an empty client note", () => {
    const updated = appendClientOwnedConversationContent(
      { ...conversation, content_html: "" },
      {
        user_id: "user-1",
        kind: "deepspace",
        title: "New import",
        recovery_title: "Research plan",
        recovery_content_html: "<p>Recovered text.</p>",
        recovery_expected_updated_at: Date.parse(conversation.updated_at),
        content_html: "<p>New import.</p>",
      },
      "2026-10-23T12:03:00.000Z",
    );

    expect(updated).toMatchObject({
      title: "Research plan",
      content_html:
        '<p>Recovered text.</p><hr data-averqel-document-separator="true" /><p>New import.</p>',
    });
  });

  it("replaces an older nonempty client copy with a confirmed newer recovery copy", () => {
    const updated = appendClientOwnedConversationContent(
      { ...conversation, content_html: "<p>Stale client copy.</p>" },
      {
        user_id: "user-1",
        kind: "deepspace",
        recovery_title: "Recovered title",
        recovery_content_html: "<p>Recovered text.</p>",
        recovery_expected_updated_at: Date.parse(conversation.updated_at),
        content_html: "<p>New section.</p>",
      },
      "2026-10-23T12:04:00.000Z",
    );

    expect(updated).toMatchObject({
      title: "Recovered title",
      content_html:
        '<p>Recovered text.</p><hr data-averqel-document-separator="true" /><p>New section.</p>',
    });
  });

  it("does not overwrite a client note changed after the recovery read", () => {
    expect(() =>
      appendClientOwnedConversationContent(
        { ...conversation, updated_at: "2026-10-23T12:05:00.000Z" },
        {
          user_id: "user-1",
          kind: "deepspace",
          recovery_content_html: "<p>Recovered text.</p>",
          recovery_expected_updated_at: Date.parse(conversation.updated_at),
          content_html: "<p>New section.</p>",
        },
      ),
    ).toThrow("Note changed while its recovery copy was being restored");
  });
});
