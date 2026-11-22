import type { Metadata } from "next";

import { UnavailableModule } from "@/components/unavailable-module";

export const metadata: Metadata = {
  title: "Analytics",
};

export default function AnalyticsPage() {
  return (
    <UnavailableModule
      title="Analytics"
      description="Operational analytics are not available in this release."
    />
  );
}
