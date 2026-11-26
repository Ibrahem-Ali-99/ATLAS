import Link from "next/link";

import { LaunchDemoButton } from "@/components/public/launch-demo-button";
import { publicNav } from "@/lib/public-site";

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:px-6 md:grid-cols-[1.4fr_1fr]">
        <div>
          <p className="font-semibold tracking-tight">ATLAS</p>
          <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
            An organization-scoped workspace for CRM, inbox, knowledge, approvals, and automation.
            Harbor & Co. and Northwind are fictional. This site publishes no customer counts, testimonials, or partnerships.
          </p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-2 text-sm">
          {publicNav.map((item) => (
            <Link key={item.href} href={item.href} className="rounded-md py-1 text-muted-foreground hover:text-foreground">
              {item.label}
            </Link>
          ))}
          <Link href="/login" className="rounded-md py-1 text-muted-foreground hover:text-foreground">
            Sign in
          </Link>
          <LaunchDemoButton label="Interactive demo" size="sm" />
        </nav>
      </div>
    </footer>
  );
}
