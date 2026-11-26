import type { Metadata } from "next";

import { ResetPasswordScreen } from "@/components/screens/password-recovery-screen";

export const metadata: Metadata = { title: "Reset password", referrer: "no-referrer" };

export default function ResetPasswordPage() {
  return <ResetPasswordScreen />;
}
