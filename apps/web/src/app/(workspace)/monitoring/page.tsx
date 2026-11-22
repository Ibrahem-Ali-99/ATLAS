import type { Metadata } from "next";

import { MonitoringScreen } from "@/components/monitoring/monitoring-screen";

export const metadata: Metadata = {
  title: "Monitoring",
};

export default function MonitoringPage() {
  return <MonitoringScreen />;
}
