import type { Metadata } from "next";

import { OverviewScreen } from "@/components/screens/overview-screen";

export const metadata: Metadata = {
  title: "Overview",
};
export const instant = false;

export default function OverviewPage() {
  return <OverviewScreen />;
}
