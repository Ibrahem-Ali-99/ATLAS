import type { Metadata } from "next";
import { Suspense } from "react";
import { InboxScreen } from "@/components/inbox/inbox-screen";
import { Skeleton } from "@/components/ui/skeleton";
export const metadata: Metadata = { title: "Inbox" };
export const instant = false;
export default function InboxPage() {
  return <Suspense fallback={<Skeleton className="h-64 w-full" />}><InboxScreen /></Suspense>;
}
