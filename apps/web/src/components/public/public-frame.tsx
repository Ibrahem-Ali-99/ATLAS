import type { ReactNode } from "react";

import { SiteFooter } from "@/components/public/site-footer";
import { SiteHeader } from "@/components/public/site-header";

export function PublicFrame({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-[16px] leading-7 text-foreground">
      <SiteHeader />
      <main id="content">{children}</main>
      <SiteFooter />
    </div>
  );
}
