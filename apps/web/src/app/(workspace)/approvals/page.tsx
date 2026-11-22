import type { Metadata } from "next";

import { UnavailableModule } from "@/components/unavailable-module";

export const metadata: Metadata = {
  title: "Approvals",
};

export default function ApprovalsPage() {
  return (
    <UnavailableModule
      title="Approvals"
      description="Human approval queues are not available in this release."
    />
  );
}
