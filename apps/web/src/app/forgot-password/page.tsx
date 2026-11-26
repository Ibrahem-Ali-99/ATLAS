import type { Metadata } from "next";

import { ForgotPasswordScreen } from "@/components/screens/password-recovery-screen";

export const metadata: Metadata = { title: "Forgot password" };

export default function ForgotPasswordPage() {
  return <ForgotPasswordScreen />;
}
