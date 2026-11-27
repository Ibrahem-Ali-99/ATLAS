"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { Session } from "@/data/session";
import { SignIn } from "@/presentation/sign-in";

export default function AcceptInvitationPage() {
  const router = useRouter();
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const stored = localStorage.getItem("atlas-theme");
    if (stored === "dark" || stored === "light") setTheme(stored);
  }, []);
  return (
    <SignIn
      theme={theme}
      mode="invite"
      onThemeChange={() => setTheme((current) => current === "light" ? "dark" : "light")}
      onComplete={(session: Session) => {
        void session;
        router.push("/");
      }}
    />
  );
}
