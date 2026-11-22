import type { Metadata } from "next";

import { CrmScreen } from "@/components/crm/crm-screen";

export const metadata: Metadata = {
  title: "CRM",
};

export default function CrmPage() {
  return <CrmScreen />;
}
