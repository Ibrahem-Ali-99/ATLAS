import type { Metadata } from "next";

import { HomeScreen } from "@/components/public/home-screen";
import { PublicFrame } from "@/components/public/public-frame";

export const metadata: Metadata = {
  title: "Operations workspace",
  description:
    "ATLAS is an organization-scoped workspace for CRM, inbox, knowledge retrieval, approvals, and workflow automation.",
};

export default function PublicHomePage() {
  return (
    <PublicFrame>
      <HomeScreen />
    </PublicFrame>
  );
}
