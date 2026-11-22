import type { Metadata } from "next";
import { Suspense } from "react";

import { MonitoringScreen } from "@/components/monitoring/monitoring-screen";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "Monitoring",
};

export default function MonitoringPage() {
  return (
    <Suspense fallback={<Skeleton className="h-40 w-full" />}>
      <MonitoringScreen />
    </Suspense>
  );
}
