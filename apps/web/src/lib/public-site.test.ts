import assert from "node:assert/strict";
import test from "node:test";

import {
  captures,
  evaluationEvidence,
  fitsLandscapeFrame,
  homepageStages,
  integrations,
  isReleaseCapture,
  landscapeCropFraction,
  landscapeCropLimit,
  landscapeFrame,
  publicNav,
  releaseShotPlan,
  retrievalComparison,
} from "./public-site.ts";

test("homepage stages fit the 16:10 frame", () => {
  for (const capture of Object.values(homepageStages)) {
    assert.ok(capture.width > capture.height, capture.src);
    assert.ok(fitsLandscapeFrame(capture), capture.src);
    assert.ok(landscapeCropFraction(capture.width, capture.height) <= landscapeCropLimit);
  }
});

test("tall and phone captures stay off the desktop stages", () => {
  const staged = new Set<string>(Object.values(homepageStages).map((item) => item.src));
  const held = [
    captures.knowledge,
    captures.crm,
    captures.lead,
    captures.runs,
    captures.analytics,
    captures.monitoring,
    captures.rejected,
    captures.mobile,
  ];
  for (const capture of held) {
    assert.equal(staged.has(capture.src), false, capture.src);
    assert.equal(fitsLandscapeFrame(capture), false, capture.src);
  }
});

test("evaluation figures are the recorded suite results", () => {
  assert.equal(evaluationEvidence.checkedOn, "26 November 2026");
  assert.deepEqual(evaluationEvidence.api, { passed: 284, skipped: 1, failed: 0 });
  assert.deepEqual(evaluationEvidence.browser, { passed: 37, skipped: 2, failed: 0 });
  assert.equal(evaluationEvidence.frontend.passed, 12);
  assert.equal(evaluationEvidence.frontend.failed, 0);
  assert.equal(evaluationEvidence.buildPassed, true);
  assert.match(evaluationEvidence.caveat, /not a clean checkout of 44631e1/);
  assert.match(evaluationEvidence.caveat, /did not send a message or create a charge/);
});

test("current portfolio files are not release captures", () => {
  for (const capture of Object.values(captures)) {
    assert.equal(capture.releaseReady, false, capture.src);
    assert.equal(isReleaseCapture(capture), false, capture.src);
  }
  for (const capture of Object.values(homepageStages)) {
    assert.equal(isReleaseCapture(capture), false);
  }
  assert.deepEqual(releaseShotPlan, [
    "Overview",
    "CRM",
    "Inbox",
    "Assistant",
    "Knowledge",
    "Workflows",
    "Analytics",
    "Integrations",
  ]);
  assert.deepEqual(landscapeFrame, { width: 1440, height: 900 });
});

test("the recorded retrieval comparison stays scoped to the small corpus", () => {
  assert.equal(retrievalComparison.recordedOn, "26 November 2026");
  assert.equal(retrievalComparison.documents, 7);
  assert.equal(retrievalComparison.questions, 8);
  assert.equal(retrievalComparison.heldOutRecorded, false);
  assert.equal(retrievalComparison.rows.find((row) => row.measure === "Recall@5")?.baseline, "0.4167");
  assert.equal(retrievalComparison.rows.find((row) => row.measure === "Recall@5")?.hybrid, "1.0000");
  assert.equal(retrievalComparison.rows.find((row) => row.measure === "Abstention accuracy")?.baseline, "0.6250");
  assert.equal(retrievalComparison.rows.find((row) => row.measure === "Mean retrieval latency")?.hybrid, "9.73 ms");
});

test("public navigation still opens the demo and the case study", () => {
  assert.ok(publicNav.some((item) => item.href === "/demo"));
  assert.ok(publicNav.some((item) => item.href === "/case-study"));
  assert.equal(integrations.length, 10);
});
