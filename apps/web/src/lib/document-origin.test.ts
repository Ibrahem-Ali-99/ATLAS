import assert from "node:assert/strict";
import test from "node:test";

// @ts-expect-error Node's strip-types test runner requires explicit TypeScript extensions.
import { documentOriginLabel, documentOrigins } from "./records.ts";
// @ts-expect-error Node's strip-types test runner requires explicit TypeScript extensions.
import { documentUploadForm } from "./document-upload.ts";

test("operational is the default supported document origin", () => {
  assert.equal(documentOrigins[0], "operational");
  assert.deepEqual(documentOrigins, ["operational", "demo"]);
});

test("invalid origins are not accepted by the UI choices", () => {
  assert.equal(documentOrigins.includes("evaluation" as never), false);
  assert.equal(documentOrigins.includes("unknown" as never), false);
});

test("stored origins are displayed with the correct labels", () => {
  assert.equal(documentOriginLabel("operational"), "Operational");
  assert.equal(documentOriginLabel("demo"), "Demo");
});

test("selecting demo sends origin=demo in multipart form data", () => {
  const form = documentUploadForm(new File(["fictional"], "test.txt"), "demo");
  assert.equal(form.get("origin"), "demo");
});
