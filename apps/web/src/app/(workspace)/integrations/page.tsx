import type { Metadata } from "next";
import { Suspense } from "react";

import { SettingsScreen } from "@/components/screens/settings-screen";

export const metadata: Metadata = {
  title: "Integrations",
};
export const instant = false;

export default function IntegrationsPage() {
  return <Suspense><SettingsScreen integrationsOnly /></Suspense>;
}
