"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function DeepSpaceInlineMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{ p: ({ children }) => <>{children}</> }}
    >
      {content}
    </ReactMarkdown>
  );
}
