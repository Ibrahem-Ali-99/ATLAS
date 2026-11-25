import type { Metadata } from "next";
import { Suspense } from "react";

import { InvitationAcceptScreen } from "@/components/screens/invitation-accept-screen";

export const metadata: Metadata = { title: "Accept invitation" };

export default function InvitationAcceptPage() {
  return <Suspense fallback={<div className="p-6">Loading invitation…</div>}><InvitationAcceptScreen /></Suspense>;
}
