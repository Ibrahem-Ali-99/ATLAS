import { expect, test } from "@playwright/test";
import { signInAsSeedAdmin } from "./auth";
import { sandboxEmailSubjects } from "./sandbox-mail";

test("a consented campaign reaches the sandbox once and its receipt survives reload", async ({ page, request }) => {
  const stamp = Date.now();
  const contact = `Consent contact ${stamp}`;
  const address = `consent-${stamp}@example.com`;
  const segment = `Consented audience ${stamp}`;
  const campaign = `Capacity update ${stamp}`;
  await signInAsSeedAdmin(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/crm?tab=contacts");
  await page.getByRole("button", { name: "New contact" }).click();
  const contactForm = page.getByRole("dialog", { name: "New contact" });
  await contactForm.getByLabel("Name", { exact: true }).fill(contact);
  await contactForm.getByLabel("Email", { exact: true }).fill(address);
  await contactForm.getByRole("button", { name: "Create", exact: true }).click();
  const consent = page.getByRole("region", { name: "Marketing consent" });
  await expect(consent.getByText("No consent recorded")).toBeVisible();
  await consent.getByLabel("Consent decision").selectOption("granted");
  await consent.getByLabel("Consent source").fill("Browser acceptance");
  await consent.getByRole("button", { name: "Save consent" }).click();
  await expect(consent.getByText("Granted · Browser acceptance")).toBeVisible();

  await page.goto("/campaigns");
  await page.getByLabel("Segment name").fill(segment);
  await page.getByLabel("Segment field").selectOption("contact_email");
  await page.getByLabel("Segment value").fill(address);
  await page.getByRole("button", { name: "Save segment" }).click();
  await expect(page.getByRole("button", { name: new RegExp(segment) })).toBeVisible();
  await page.getByRole("button", { name: "New campaign" }).click();
  const editor = page.getByRole("dialog", { name: "New campaign" });
  await editor.getByLabel("Campaign name").fill(campaign);
  await editor.getByLabel("Campaign segment").selectOption({ label: segment });
  await editor.getByLabel("Email subject").fill("Capacity update");
  await editor.getByLabel("Email body").fill("New storage capacity is available.");
  await editor.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("dialog", { name: campaign })).toBeVisible();
  await page.keyboard.press("Escape");
  const review = page.getByRole("region", { name: "Campaign review" });
  await expect(review.getByRole("heading", { name: campaign })).toBeVisible();
  const eligible = review.getByTestId("campaign-audience-eligible-addresses");
  await expect(eligible).toHaveText("1");

  await review.getByRole("button", { name: "Schedule delivery" }).click();
  const delivery = page.getByRole("dialog", { name: "Schedule sandbox delivery" });
  await delivery.getByRole("button", { name: "Send to sandbox" }).click();
  await expect(review.getByText("Accepted by sandbox")).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => sandboxEmailSubjects(request, address)).toEqual(["Capacity update"]);

  await review.getByText("Recipient delivery status").click();
  await expect(review.getByRole("list", { name: "Campaign recipients" }).getByText(address)).toBeVisible();
  await page.getByRole("button", { name: "Suppressions" }).click();
  const suppress = page.getByRole("dialog", { name: "Campaign suppressions" });
  if (process.env.ATLAS_E2E_SKIP_MAILPIT === "1") {
    const api = `http://127.0.0.1:${process.env.ATLAS_E2E_API_PORT ?? "8011"}`;
    const accepted = await request.get(`${api}/_acceptance/mail`, { params: { recipient: address } });
    expect(accepted.ok()).toBeTruthy();
    const [message] = await accepted.json() as { body: string }[];
    const unsubscribe = message.body.match(/Unsubscribe: (https?:\/\/\S+)/)?.[1];
    if (!unsubscribe) throw new Error("The received campaign email had no unsubscribe link");
    const preference = await page.context().newPage();
    try {
      await preference.goto(unsubscribe);
      await expect(preference.getByRole("heading", { name: "Unsubscribe from campaign emails" })).toBeVisible();
      await preference.getByRole("button", { name: "Unsubscribe", exact: true }).click();
      await expect(preference.getByRole("heading", { name: "Unsubscribed", exact: true })).toBeVisible();
    } finally {
      await preference.close();
    }
    await suppress.getByRole("button", { name: "Close" }).click();
    await page.getByRole("button", { name: "Suppressions" }).click();
    await expect(suppress.getByRole("region", { name: "Suppressed addresses" }).getByText(address)).toBeVisible();
  } else {
    await suppress.getByLabel("Email address").fill(address);
    await suppress.getByRole("button", { name: "Suppress address" }).click();
    await expect(suppress.getByRole("status")).toContainText("was excluded");
  }
  await suppress.getByRole("button", { name: "Close" }).click();
  await expect(review.getByRole("button", { name: "Schedule delivery" })).toHaveCount(0);
  await page.reload();
  await expect(review.getByText("New storage capacity is available.")).toBeVisible();
  await expect(review.getByText("Accepted by sandbox")).toBeVisible();
  expect(await sandboxEmailSubjects(request, address)).toEqual(["Capacity update"]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});
