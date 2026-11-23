import {
  Activity,
  BarChart3,
  BookOpen,
  Bot,
  CheckCheck,
  LayoutDashboard,
  Settings,
  ListChecks,
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

export type NavGroup = {
  label: string;
  items: NavItem[];
};

const overview = { href: "/overview", label: "Overview", icon: LayoutDashboard };
const assistant = { href: "/assistant", label: "AI Assistant", icon: Sparkles };
const crm = { href: "/crm", label: "CRM", icon: Users };
const knowledge = { href: "/knowledge", label: "Knowledge", icon: BookOpen };
const agentRuns = { href: "/agent-runs", label: "Agent Runs", icon: Bot };
const approvals = { href: "/approvals", label: "Approvals", icon: CheckCheck };
const workflows = { href: "/workflows", label: "Workflows", icon: Workflow };
const analytics = { href: "/analytics", label: "Analytics", icon: BarChart3 };
const monitoring = { href: "/monitoring", label: "Monitoring", icon: Activity };
const settings = { href: "/settings", label: "Settings", icon: Settings };
const setup = { href: "/setup", label: "First-run setup", icon: ListChecks };

export const navigationGroups: NavGroup[] = [
  { label: "Business operations", items: [overview, assistant, crm, knowledge] },
  { label: "Operations", items: [agentRuns, approvals, workflows] },
  { label: "Insight", items: [analytics, monitoring, setup, settings] },
];

export const navigation: NavItem[] = navigationGroups.flatMap((group) => group.items);

export function titleForPath(pathname: string): string {
  return navigation.find((item) => item.href === pathname)?.label ?? "ATLAS";
}
