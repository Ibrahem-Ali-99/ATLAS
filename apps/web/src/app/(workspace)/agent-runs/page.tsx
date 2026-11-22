import type { Metadata } from "next";

import { UnavailableModule } from "@/components/unavailable-module";

export const metadata: Metadata = {
  title: "Agent Runs",
};

export default function AgentRunsPage() {
  return (
    <UnavailableModule
      title="Agent Runs"
      description="Agent execution history is not available in this release."
    />
  );
}
