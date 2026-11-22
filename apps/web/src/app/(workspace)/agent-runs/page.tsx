import type { Metadata } from "next";

import { AgentRunsScreen } from "@/components/agent-runs/agent-runs-screen";

export const metadata: Metadata = {
  title: "Agent Runs",
};

export default function AgentRunsPage() {
  return <AgentRunsScreen />;
}
