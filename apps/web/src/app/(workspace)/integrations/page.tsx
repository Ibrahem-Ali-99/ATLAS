import type { Metadata } from "next";

import { SettingsScreen } from "@/components/screens/settings-screen";

export const metadata: Metadata = {
  title: "Integrations",
};

export default function IntegrationsPage() {
  return <SettingsScreen integrationsOnly />;
}
