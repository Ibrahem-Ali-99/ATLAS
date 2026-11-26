import type { APIRequestContext } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

export async function sandboxEmailSubjects(request: APIRequestContext, recipient: string): Promise<string[]> {
  const apiPort = process.env.ATLAS_E2E_API_PORT ?? "8011";
  if (process.env.ATLAS_E2E_SKIP_MAILPIT === "1") {
    const response = await request.get(`http://127.0.0.1:${apiPort}/_acceptance/mail`, { params: { recipient } });
    if (!response.ok()) throw new Error(`The local SMTP sink returned ${response.status()}`);
    const messages = await response.json() as { subject: string }[];
    return messages.map((message) => message.subject);
  }
  const portFile = path.resolve(process.cwd(), `../../var/e2e-mailpit-${apiPort}.http-port`);
  const mailpitPort = readFileSync(portFile, "utf8").trim();
  if (!/^\d+$/.test(mailpitPort)) throw new Error("The disposable Mailpit HTTP port was not recorded");
  const response = await request.get(`http://127.0.0.1:${mailpitPort}/api/v1/messages`);
  if (!response.ok()) throw new Error(`Mailpit returned ${response.status()}`);
  const { messages } = await response.json() as { messages: { To: { Address: string }[]; Subject: string }[] };
  return messages.filter((message) => message.To.some(({ Address }) => Address.toLowerCase() === recipient.toLowerCase()))
    .map((message) => message.Subject);
}
