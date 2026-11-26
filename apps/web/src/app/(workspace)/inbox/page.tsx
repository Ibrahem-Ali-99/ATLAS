import type { Metadata } from "next";
import { InboxScreen } from "@/components/inbox/inbox-screen";
export const metadata: Metadata = { title: "Inbox" };
export const instant = false;
export default function InboxPage() { return <InboxScreen />; }
