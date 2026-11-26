import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";

const workspaceName = "ATLAS Sample Workspace";

export function sampleWorkspaceSlug(): string {
  return `sample-e2e-${process.pid}-${Date.now()}`;
}

export async function prepareSampleWorkspace(request: APIRequestContext, slug: string, operation: "prepare" | "verify" | "cleanup"): Promise<void> {
  const apiPort = process.env.ATLAS_E2E_API_PORT ?? "8011";
  const response = await request.post(`http://127.0.0.1:${apiPort}/_acceptance/sample-workspace/${slug}`, {
    params: { operation },
    timeout: 15_000,
  });
  expect(response.ok(), `Disposable workspace ${operation}: ${response.status()}`).toBe(true);
}

export async function openSampleWorkspace(page: Page): Promise<void> {
  await signInAsSeedAdmin(page);
  const selector = page.getByLabel("Organization");
  await selector.selectOption({ label: workspaceName });
  await expect(selector.locator("option:checked")).toHaveText(workspaceName);
}
