import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, apiFetch, apiStream, setCsrfToken } from "./client.ts";

test("apiFetch builds JSON requests with CSRF and normalizes API errors", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Request[] = [];
  setCsrfToken("csrf-123");
  globalThis.fetch = async (_input, init) => {
    calls.push(new Request("http://atlas.test/api", init));
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
  };
  try {
    await assert.doesNotReject(() => apiFetch<{ ok: boolean }>("/api/test", { method: "POST", body: JSON.stringify({ value: 1 }) }));
    assert.equal(calls[0]?.headers.get("Content-Type"), "application/json");
    assert.equal(calls[0]?.headers.get("X-CSRF-Token"), "csrf-123");
    assert.equal(calls[0]?.credentials, "include");
    assert.equal(calls[0]?.cache, "no-store");

    globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: "forbidden", message: "Not allowed" } }), { status: 403 });
    await assert.rejects(() => apiFetch("/api/denied"), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 403);
      assert.equal(error.code, "forbidden");
      return true;
    });
  } finally {
    globalThis.fetch = originalFetch;
    setCsrfToken(null);
  }
});

test("apiStream consumes token, phase, and done SSE events", async () => {
  const originalFetch = globalThis.fetch;
  const events: string[] = [];
  const phases: string[] = [];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      controller.enqueue(encoder.encode('event: token\ndata: {"text":"Hello"}\n\n'));
      controller.enqueue(encoder.encode('event: phase\ndata: {"phase":"retrieving"}\n\n'));
      controller.enqueue(encoder.encode('event: done\ndata: {"answer":"Hello"}\n\n'));
      controller.close();
    },
  });
  globalThis.fetch = async () => new Response(stream, { status: 200 });
  try {
    const result = await apiStream<{ answer: string }>("/api/stream", { content: "Hi" }, (text) => events.push(text), (phase) => phases.push(phase));
    assert.deepEqual(events, ["Hello"]);
    assert.deepEqual(phases, ["retrieving"]);
    assert.deepEqual(result, { answer: "Hello" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
