import assert from "node:assert/strict";
import { test } from "node:test";
import { apiFetch } from "./client.ts";
import { getSession, login, logout } from "./session.ts";

const session = {
  user: { id: "user-1", email: "person@example.com", full_name: "Person Example" },
  memberships: [{ id: "membership-1", organization_id: "org-1", organization_name: "Example", organization_slug: "example", role: "admin" as const }],
  csrf_token: "csrf-session",
};

test("session APIs use the auth contracts and retain the CSRF token", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Request[] = [];
  globalThis.fetch = async (input, init) => {
    const request = new Request(new URL(String(input), "http://localhost").toString(), init);
    requests.push(request);
    if (request.url.endsWith("/login") || request.url.endsWith("/auth/me")) return Response.json(session);
    return new Response(null, { status: 204 });
  };
  try {
    const loggedIn = await login("person@example.com", "password");
    assert.equal(loggedIn.user.id, "user-1");
    await apiFetch("/api/protected", { method: "POST", body: JSON.stringify({ ok: true }) });
    await getSession();
    await logout();
    assert.equal(requests[0]?.url, "http://localhost/api/v1/auth/login");
    assert.equal(requests[0]?.method, "POST");
    assert.equal(requests[1]?.headers.get("X-CSRF-Token"), "csrf-session");
    assert.equal(requests[2]?.url, "http://localhost/api/v1/auth/me");
    assert.equal(requests[3]?.headers.get("X-CSRF-Token"), "csrf-session");
    assert.equal(requests[3]?.method, "POST");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
