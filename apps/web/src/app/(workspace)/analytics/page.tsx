import type { Metadata } from "next";

import { AnalyticsScreen } from "@/components/analytics/analytics-screen";

export const metadata: Metadata = {
  title: "Analytics",
};
export const instant = false;

export default function AnalyticsPage() {
  return <AnalyticsScreen />;
}
