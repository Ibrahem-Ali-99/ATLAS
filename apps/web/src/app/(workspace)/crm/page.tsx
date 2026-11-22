import type { Metadata } from "next";

import { UnavailableModule } from "@/components/unavailable-module";

export const metadata: Metadata = {
  title: "CRM",
};

export default function CrmPage() {
  return (
    <UnavailableModule
      title="CRM"
      description="Customer records, accounts, and pipeline data are not available in this release."
    />
  );
}
