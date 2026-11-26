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

test("Harbor frames stay off the site until the redesigned workspace is captured", () => {
  const held = [
    captures.overview,
    captures.crm,
    captures.inbox,
    captures.knowledge,
    captures.workflows,
    captures.analytics,
    captures.integrations,
    captures.assistant,
  ];
  for (const capture of held) {
    assert.equal(capture.releaseReady, false, capture.src);
    assert.equal(isReleaseCapture(capture), false, capture.src);
  }
  assert.equal(isReleaseCapture(homepageStages.assistant), false);
  assert.equal(isReleaseCapture(homepageStages.hero), false);
  assert.equal(isReleaseCapture(homepageStages.automation), false);
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

test("the recorded retrieval evaluation keeps the missed targets", () => {
  assert.equal(retrievalComparison.recordedOn, "26 November 2026");
  assert.equal(retrievalComparison.pipeline, "answerable");
  assert.equal(retrievalComparison.ploverQuestions, 45);
  assert.equal(retrievalComparison.orryQuestions, 26);
  assert.equal(retrievalComparison.publicInference, false);
  assert.equal(retrievalComparison.rows.find((row) => row.measure === "Recall@5")?.plover, "0.9286");
  assert.equal(retrievalComparison.rows.find((row) => row.measure === "Recall@5")?.target, "0.85");
  assert.equal(retrievalComparison.rows.find((row) => row.measure === "Abstention accuracy")?.plover, "0.8000");
  assert.equal(retrievalComparison.rows.find((row) => row.measure === "Factual correctness")?.orry, "0.5000");
  assert.equal(retrievalComparison.rows.find((row) => row.measure === "Mean retrieval latency")?.orry, "11.62 ms");
});

test("public navigation still opens the demo and the case study", () => {
  assert.ok(publicNav.some((item) => item.href === "/demo"));
  assert.ok(publicNav.some((item) => item.href === "/case-study"));
  assert.equal(integrations.length, 10);
});
