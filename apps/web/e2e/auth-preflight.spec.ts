import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

test("disposable API accepts the seeded admin and opens the workspace", async ({ page }) => {
  await signInAsSeedAdmin(page);
  await expect(page.getByRole("link", { name: "Knowledge", exact: true })).toBeVisible();
});
