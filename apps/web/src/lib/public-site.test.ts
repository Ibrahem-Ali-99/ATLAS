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

test("older tall captures stay off the release frames", () => {
  const held = [captures.lead, captures.runs, captures.monitoring, captures.rejected, captures.mobile];
  for (const capture of held) {
    assert.equal(capture.releaseReady, false, capture.src);
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

test("Harbor frames are 1440×900 and the assistant frame is not published", () => {
  const published = [
    captures.overview,
    captures.crm,
    captures.inbox,
    captures.knowledge,
    captures.workflows,
    captures.analytics,
    captures.integrations,
  ];
  for (const capture of published) {
    assert.equal(isReleaseCapture(capture), true, capture.src);
    assert.equal(capture.frame, "Harbor & Co.");
  }
  assert.equal(captures.assistant.releaseReady, false);
  assert.equal(isReleaseCapture(captures.assistant), false);
  assert.equal(isReleaseCapture(homepageStages.assistant), false);
  assert.equal(isReleaseCapture(homepageStages.hero), true);
  assert.equal(isReleaseCapture(homepageStages.automation), true);
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
