import { BlockNoteEditor, BlockNoteSchema, defaultBlockSpecs } from "@blocknote/core";
import { Link } from "@tiptap/extension-link";
import { describe, expect, it } from "vitest";

describe("DeepSpace note link marks", () => {
  it("parses linked italic text without creating an invalid mark set", () => {
    const editor = BlockNoteEditor.create({
      schema: BlockNoteSchema.create({ blockSpecs: defaultBlockSpecs }),
      disableExtensions: ["link"],
      _tiptapOptions: {
        extensions: [Link.extend({ priority: 100 }).configure({ protocols: [] })],
      },
    });

    try {
      const blocks = editor.tryParseHTMLToBlocks(
        '<p><em><a href="https://example.com">linked italic text</a></em></p>',
      );

      expect(() => editor.replaceBlocks(editor.document, blocks)).not.toThrow();
    } finally {
      editor._tiptapEditor.destroy();
    }
  });
});
