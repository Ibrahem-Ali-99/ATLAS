import assert from "node:assert/strict";
import test from "node:test";

import {
  captures,
  evaluationEvidence,
  fitsLandscapeFrame,
  homepageStages,
  integrations,
  landscapeCropFraction,
  landscapeCropLimit,
  publicNav,
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

test("public navigation still opens the demo and the case study", () => {
  assert.ok(publicNav.some((item) => item.href === "/demo"));
  assert.ok(publicNav.some((item) => item.href === "/case-study"));
  assert.equal(integrations.length, 10);
});
