import assert from "node:assert/strict";
import test from "node:test";

import {
  formatCatalogUsd,
  formatKnowledgeBytes,
  planPrice,
  publicPlans,
} from "./public-catalog.ts";

test("the public catalog matches the stored plan limits and Stripe test amounts", () => {
  assert.deepEqual(
    publicPlans.map((plan) => [plan.code, plan.seats, plan.assistantRequests, plan.knowledgeBytes, plan.activeWorkflows, plan.monthlyCents, plan.yearlyCents]),
    [
      ["free", 2, 100, 1_000_000_000, 2, null, null],
      ["starter", 5, 1_000, 10_000_000_000, 10, 1_900, 19_000],
      ["pro", 20, 5_000, 100_000_000_000, 50, 4_900, 49_000],
      ["business", 100, 25_000, 1_000_000_000_000, 200, 9_900, 99_000],
    ],
  );
});

test("catalog prices format as whole US dollars", () => {
  assert.equal(formatCatalogUsd(1_900), "$19");
  assert.equal(formatCatalogUsd(99_000), "$990");
  assert.equal(planPrice(publicPlans[0], "monthly"), "Included");
  assert.equal(planPrice(publicPlans[2], "yearly"), "$490");
  assert.equal(formatKnowledgeBytes(1_000_000_000), "1 GB");
  assert.equal(formatKnowledgeBytes(1_000_000_000_000), "1 TB");
});
