import type { Metadata } from "next";
import { Suspense } from "react";

import { AgentRunsScreen } from "@/components/agent-runs/agent-runs-screen";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "Agent Runs",
};
export const instant = false;

export default function AgentRunsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-40 w-full" />}>
      <AgentRunsScreen />
    </Suspense>
  );
}
