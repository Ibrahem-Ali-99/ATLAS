import type { Metadata } from "next";

import { WorkflowsScreen } from "@/components/workflows/workflows-screen";

export const metadata: Metadata = {
  title: "Workflows",
};

export default async function WorkflowsPage({ searchParams }: {
  searchParams: Promise<{ workflow?: string | string[]; run?: string | string[]; archived?: string | string[] }>;
}) {
  const { workflow, run, archived } = await searchParams;
  return <WorkflowsScreen
    key={`${workflow ?? ""}:${run ?? ""}`}
    requestedWorkflow={typeof workflow === "string" ? workflow : undefined}
    requestedRun={typeof run === "string" ? run : undefined}
    showArchived={archived === "1"}
  />;
}
