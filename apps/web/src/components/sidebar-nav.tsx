"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { navigationGroups } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export function SidebarNav({
  organizationName,
  onNavigate,
}: {
  organizationName?: string | null;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col px-4 py-6 text-white">
      <p className="px-2 text-[22px] font-semibold leading-none"><span className="text-[#b3a7ff]">A</span> atlas</p>
      <div className="mt-8 rounded-lg bg-[#202d46] px-3 py-3">
        <p className="truncate text-sm font-semibold">{organizationName ?? "Business operations"}</p>
        <p className="mt-1 text-[10px] text-[#91a0bb]">Workspace / Business</p>
      </div>
      <nav className="mt-6 flex flex-1 flex-col gap-6" aria-label="Workspace">
        {navigationGroups.map((group) => (
          <div key={group.label} className="flex flex-col gap-1">
            <div className="flex flex-col">
              {group.items.map((item) => {
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={onNavigate}
                    className={cn(
                      "flex h-9 items-center rounded-md px-3 text-sm text-[#aab5cb] transition-colors hover:bg-[#202d46] hover:text-white",
                      active && "bg-[#3a315f] font-medium text-white hover:bg-[#3a315f]",
                    )}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="border-t border-white/10 pt-5 text-[11px] text-[#72d5bb]">● All systems operational</div>
      <div className="mt-3 px-1 text-[10px] text-[#71809b]">ATLAS / v1.0</div>
    </div>
  );
}
