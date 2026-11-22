import type { Metadata } from "next";
import { Suspense } from "react";

import { CrmScreen } from "@/components/crm/crm-screen";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
  title: "CRM",
};

export default function CrmPage() {
  return (
    <Suspense fallback={<Skeleton className="h-40 w-full" />}>
      <CrmScreen />
    </Suspense>
  );
}
