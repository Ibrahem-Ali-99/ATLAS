import { expect, type Page } from "@playwright/test";

export type SeedUser = "admin" | "staff" | "outsider";

const seedCredentials: Record<SeedUser, { email: string; password: string }> = {
  admin: { email: "admin@example.com", password: "change-me-admin" },
  staff: { email: "staff@example.com", password: "change-me-staff" },
  outsider: { email: "outsider@example.org", password: "change-me-outsider" },
};

export async function signInAsSeedUser(page: Page, user: SeedUser = "admin"): Promise<void> {
  const credentials = seedCredentials[user];
  const loginResponse = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login"),
  );
  await page.goto("/login");
  await page.getByLabel("Email").fill(credentials.email);
  await page.getByLabel("Password").fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  const response = await loginResponse;
  const body = (await response.json().catch(() => ({}))) as { detail?: { code?: string } };
  console.log(
    `e2e_login_status=${response.status()} api=${new URL(response.url()).origin} database=atlas_e2e`,
  );
  expect(
    response.ok(),
    `login failed: status=${response.status()} code=${body.detail?.code ?? "none"} url=${response.url()}`,
  ).toBe(true);
  await page.waitForURL(/\/overview(?:\?|$)/);
  await expect(page.getByRole("main")).toBeVisible();
}

export const signInAsSeedAdmin = (page: Page): Promise<void> => signInAsSeedUser(page, "admin");
export const signInAsSeedStaff = (page: Page): Promise<void> => signInAsSeedUser(page, "staff");
export const signInAsSeedOutsider = (page: Page): Promise<void> => signInAsSeedUser(page, "outsider");
