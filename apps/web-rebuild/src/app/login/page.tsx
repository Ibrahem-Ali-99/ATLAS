import type { Metadata } from "next";

import { Workspace } from "@/presentation/workspace";

export const metadata: Metadata = {
  title: "Sign in · ATLAS",
  description: "Sign in to an ATLAS workspace.",
};

export default function LoginPage() {
  return <Workspace />;
}
