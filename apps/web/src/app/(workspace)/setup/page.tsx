import type { Metadata } from "next";

import { SetupScreen } from "@/components/screens/setup-screen";

export const metadata: Metadata = { title: "First-run setup" };

export default function SetupPage() {
  return <SetupScreen />;
}
