import Link from "next/link";

import { LaunchDemoButton } from "@/components/public/launch-demo-button";
import { footerNav } from "@/lib/public-site";

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:px-8 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div>
          <p className="font-semibold tracking-tight">ATLAS</p>
          <p className="mt-3 max-w-md text-sm leading-6 text-muted-foreground">
            An organization-scoped workspace for CRM, inbox, knowledge, approvals, and automation.
            Harbor & Co. and Northwind are fictional. This site publishes no customer counts, testimonials, or partnerships.
          </p>
        </div>
        <div className="grid content-start gap-6 sm:grid-cols-[1fr_auto]">
          <nav aria-label="Footer" className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            {footerNav.map((item) => (
              <Link key={item.href} href={item.href} className="rounded-md py-1 text-muted-foreground hover:text-foreground">
                {item.label}
              </Link>
            ))}
          </nav>
          <LaunchDemoButton label="Interactive demo" size="sm" />
        </div>
      </div>
    </footer>
  );
}
