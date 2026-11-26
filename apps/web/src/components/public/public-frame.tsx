import type { ReactNode } from "react";

import { SiteFooter } from "@/components/public/site-footer";
import { SiteHeader } from "@/components/public/site-header";

export function PublicFrame({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-[16px] leading-7 text-foreground">
      <style>{`@keyframes atlas-rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}`}</style>
      <SiteHeader />
      <main id="content">{children}</main>
      <SiteFooter />
    </div>
  );
}
