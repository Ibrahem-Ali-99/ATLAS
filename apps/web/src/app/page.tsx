import type { Metadata } from "next";

import { HomeScreen } from "@/components/public/home-screen";
import { PublicFrame } from "@/components/public/public-frame";

export const metadata: Metadata = {
  title: "Operations workspace",
  description:
    "ATLAS keeps CRM, inbox, documents, and automation in one organization. Answers cite retrieved records, and a person approves a message, booking, or CRM change.",
};

export default function PublicHomePage() {
  return (
    <PublicFrame>
      <HomeScreen />
    </PublicFrame>
  );
}
