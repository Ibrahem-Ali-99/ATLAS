import type { Metadata } from "next";

import { BillingScreen } from "@/components/screens/billing-screen";

export const metadata: Metadata = { title: "Billing" };
export const instant = false;

export default async function BillingPage({ searchParams }: {
  searchParams: Promise<{ checkout?: string | string[] }>;
}) {
  const { checkout } = await searchParams;
  return <BillingScreen checkout={checkout === "success" || checkout === "canceled" ? checkout : undefined} />;
}
