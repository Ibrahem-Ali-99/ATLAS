import type { Metadata } from "next";
import { Suspense } from "react";

import { ApprovalsScreen } from "@/components/approvals/approvals-screen";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "Approvals",
};
export const instant = false;

export default function ApprovalsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-40 w-full" />}>
      <ApprovalsScreen />
    </Suspense>
  );
}
