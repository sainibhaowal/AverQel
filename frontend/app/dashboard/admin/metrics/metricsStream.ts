export interface ServerSentEventMessage {
  event: string;
  data: string;
}

export async function* readServerSentEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<ServerSentEventMessage> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const parseBlock = (block: string): ServerSentEventMessage | null => {
    let event = "message";
    const data: string[] = [];

    for (const line of block.split(/\r?\n/)) {
      if (!line || line.startsWith(":")) {
        continue;
      }
      const separator = line.indexOf(":");
      const field = separator === -1 ? line : line.slice(0, separator);
      const value = separator === -1 ? "" : line.slice(separator + 1).replace(/^ /, "");
      if (field === "event") {
        event = value;
      } else if (field === "data") {
        data.push(value);
      }
    }

    return data.length ? { event, data: data.join("\n") } : null;
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? "";

      for (const block of blocks) {
        const message = parseBlock(block);
        if (message) {
          yield message;
        }
      }

      if (done) {
        const message = parseBlock(buffer);
        if (message) {
          yield message;
        }
        return;
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}
