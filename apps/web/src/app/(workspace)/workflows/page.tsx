import type { Metadata } from "next";

import { UnavailableModule } from "@/components/unavailable-module";

export const metadata: Metadata = {
  title: "Workflows",
};

export default function WorkflowsPage() {
  return (
    <UnavailableModule
      title="Workflows"
      description="Workflow automation is not available in this release."
    />
  );
}
