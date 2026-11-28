import assert from "node:assert/strict";
import { test } from "node:test";
import { bindWorkspace } from "../presentation/appConfig.ts";
import { ApiError } from "./client.ts";
import { checkoutBilling, changeMemberRole, failureMessage, getAssistantConversation, loadBilling, loadProviderStatus } from "./resources.ts";

test("resource contracts bind billing, provider status, permissions, and conversations to the workspace", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Request[] = [];
  bindWorkspace({ organizationId: "org-42", organizationName: "Example", userName: "Person Example", email: "person@example.com" });
  globalThis.fetch = async (input, init) => {
    const request = new Request(new URL(String(input), "http://localhost").toString(), init);
    requests.push(request);
    if (request.url.endsWith("/billing")) return Response.json({ mode: "sandbox", checkout_available: true, portal_available: false, subscription: {}, usage: {}, plan: {} });
    if (request.url.endsWith("/provider-status")) return Response.json({ llm_ready: true, embedding_ready: false });
    if (request.url.endsWith("/conversations/conversation-1")) return Response.json({ id: "conversation-1", title: "Test", updated_at: "2026-11-28T00:00:00Z", messages: [{ id: "message-1", role: "assistant", content: "Done", sources: [], proposals: [], steps: [] }] });
    if (request.url.endsWith("/billing/checkout")) return Response.json({ mode: "sandbox", status: "ok" });
    return Response.json({ ok: true });
  };
  try {
    const billing = await loadBilling();
    const checkout = await checkoutBilling("pro", "yearly");
    const provider = await loadProviderStatus();
    await changeMemberRole("member-7", "staff");
    const conversation = await getAssistantConversation("conversation-1");
    assert.equal(billing.mode, "sandbox");
    assert.equal(checkout.status, "ok");
    assert.equal(provider.embedding_ready, false);
    assert.equal(conversation.messages[0]?.body, "Done");
    assert.equal(requests[0]?.url, "http://localhost/api/v1/organizations/org-42/billing");
    assert.deepEqual(JSON.parse(await requests[1]!.text()), { plan_code: "pro", billing_interval: "yearly" });
    assert.equal(requests[2]?.url, "http://localhost/api/v1/organizations/org-42/provider-status");
    assert.deepEqual(JSON.parse(await requests[3]!.text()), { role: "staff" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("failureMessage preserves actionable API errors", () => {
  assert.equal(failureMessage(new ApiError(409, "conflict", "Already exists")), "Already exists");
  assert.equal(failureMessage(new Error("ignored")), "The request failed.");
});
