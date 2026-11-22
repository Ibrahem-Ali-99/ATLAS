import type { Metadata } from "next";

import { WorkflowsScreen } from "@/components/workflows/workflows-screen";

export const metadata: Metadata = {
  title: "Workflows",
};

export default function WorkflowsPage() {
  return <WorkflowsScreen />;
}
