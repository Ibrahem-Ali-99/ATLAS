import {
  BarChart3,
  BookOpen,
  LayoutDashboard,
  Settings,
  ListChecks,
  Plug,
  Activity,
  Users,
  Workflow,
  Inbox,
  Megaphone,
  BadgeCheck,
  Bot,
  Gauge,
  CreditCard,
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
const assistant = { href: "/assistant", label: "Assistant", icon: Bot };
const crm = { href: "/crm", label: "CRM", icon: Users };
const knowledge = { href: "/knowledge", label: "Knowledge", icon: BookOpen };
const inbox = { href: "/inbox", label: "Inbox", icon: Inbox };
const campaigns = { href: "/campaigns", label: "Campaigns", icon: Megaphone };
const agentRuns = { href: "/agent-runs", label: "Agent Runs", icon: Activity };
const approvals = { href: "/approvals", label: "Approvals", icon: BadgeCheck };
const automations = { href: "/workflows", label: "Workflows", icon: Workflow };
const integrations = { href: "/integrations", label: "Integrations", icon: Plug };
const analytics = { href: "/analytics", label: "Analytics", icon: BarChart3 };
const monitoring = { href: "/monitoring", label: "Monitoring", icon: Gauge };
const settings = { href: "/settings", label: "Settings", icon: Settings };
const billing = { href: "/billing", label: "Billing", icon: CreditCard };
const setup = { href: "/setup", label: "Setup", icon: ListChecks };

export const navigationGroups: NavGroup[] = [
  { label: "Work", items: [overview, crm, inbox, assistant, knowledge, approvals, automations, agentRuns, analytics, campaigns] },
  { label: "Manage", items: [monitoring, integrations, billing, settings, setup] },
];

export const navigation: NavItem[] = navigationGroups.flatMap((group) => group.items);

export function titleForPath(pathname: string): string {
  return navigation.find((item) => item.href === pathname)?.label ?? "ATLAS";
}
