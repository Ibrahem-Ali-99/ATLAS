import type { Metadata } from "next";

import { BillingScreen } from "@/components/screens/billing-screen";

export const metadata: Metadata = { title: "Billing" };
export const instant = false;

export default async function BillingPage({ searchParams }: {
  searchParams: Promise<{ checkout?: string | string[]; portal?: string | string[] }>;
}) {
  const params = await searchParams;
  const checkout = params.checkout === "success" || params.checkout === "canceled" ? params.checkout : undefined;
  return <BillingScreen checkout={checkout} portalReturn={params.portal === "return"} />;
}
