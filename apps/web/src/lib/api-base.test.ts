import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveApiBaseUrl } from "./api-base.ts";

test("an unset URL keeps the local API port", () => {
  assert.equal(resolveApiBaseUrl(undefined), "http://127.0.0.1:8000");
  assert.equal(resolveApiBaseUrl(""), "http://127.0.0.1:8000");
  assert.equal(resolveApiBaseUrl("   "), "http://127.0.0.1:8000");
});

test("same-origin uses the page host", () => {
  assert.equal(resolveApiBaseUrl("same-origin"), "");
  assert.equal(resolveApiBaseUrl(" same-origin "), "");
});

test("an explicit URL is kept and a trailing slash is removed", () => {
  assert.equal(resolveApiBaseUrl("http://127.0.0.1:8010"), "http://127.0.0.1:8010");
  assert.equal(resolveApiBaseUrl("https://staging.example.com/"), "https://staging.example.com");
});
