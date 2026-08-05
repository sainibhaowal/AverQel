"""Deterministic local OpenAI-compatible provider for isolated staging tests."""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class MockProviderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_POST(self) -> None:  # noqa: N802
        delay = float(os.environ.get("STAGING_MOCK_DELAY_SECONDS", "0") or 0)
        if delay > 0:
            time.sleep(delay)
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")

        if self.path.endswith("/embed") or self.path.endswith("/embeddings"):
            texts = body.get("input") or body.get("texts") or [""]
            if not isinstance(texts, list):
                texts = [texts]
            vectors = [[0.0] * 384 for _ in texts]
            if self.path.endswith("/embed"):
                payload = {"vectors": vectors}
            else:
                payload = {
                    "object": "list",
                    "data": [
                        {"object": "embedding", "index": i, "embedding": vector}
                        for i, vector in enumerate(vectors)
                    ],
                    "model": "staging-mock-embedding",
                }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
            return

        messages = body.get("messages") or [{"content": "synthetic"}]
        prompt = str(messages[-1].get("content", ""))[:120]
        text = f"STAGING_DEEPSPACE_VERIFIED: {prompt}"

        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for part in (text[:80], text[80:]):
                if part:
                    payload = {"choices": [{"index": 0, "delta": {"content": part}}]}
                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                    self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        payload = {
            "id": "staging-mock",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 32, "completion_tokens": 16, "total_tokens": 48},
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def log_message(self, *_args: object) -> None:
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), MockProviderHandler).serve_forever()
