import type { Metadata } from "next";
import { Suspense } from "react";

import { AssistantScreen } from "@/components/assistant/assistant-screen";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "AI Assistant",
};

export default function AssistantPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <AssistantScreen />
    </Suspense>
  );
}
