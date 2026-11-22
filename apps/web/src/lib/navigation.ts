import {
  BarChart3,
  Bot,
  CheckCheck,
  LayoutDashboard,
  Settings,
  Sparkles,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

export const navigation: NavItem[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/assistant", label: "AI Assistant", icon: Sparkles },
  { href: "/crm", label: "CRM", icon: Users },
  { href: "/agent-runs", label: "Agent Runs", icon: Bot },
  { href: "/workflows", label: "Workflows", icon: Workflow },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/approvals", label: "Approvals", icon: CheckCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function titleForPath(pathname: string): string {
  return navigation.find((item) => item.href === pathname)?.label ?? "ATLAS";
}
