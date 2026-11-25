import {
  BarChart3,
  BookOpen,
  LayoutDashboard,
  Settings,
  ListChecks,
  Plug,
  Sparkles,
  Users,
  Workflow,
  Inbox,
  Megaphone,
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
const inbox = { href: "/inbox", label: "Inbox", icon: Inbox };
const campaigns = { href: "/campaigns", label: "Campaigns", icon: Megaphone };
const automations = { href: "/workflows", label: "Workflows", icon: Workflow };
const integrations = { href: "/integrations", label: "Integrations", icon: Plug };
const analytics = { href: "/analytics", label: "Analytics", icon: BarChart3 };
const settings = { href: "/settings", label: "Settings", icon: Settings };
const setup = { href: "/setup", label: "Setup", icon: ListChecks };

export const navigationGroups: NavGroup[] = [
  { label: "Business operations", items: [overview, assistant, crm, inbox, knowledge, campaigns] },
  { label: "Automation", items: [automations, integrations] },
  { label: "Insight & administration", items: [analytics, setup, settings] },
];

export const navigation: NavItem[] = navigationGroups.flatMap((group) => group.items);

export function titleForPath(pathname: string): string {
  return navigation.find((item) => item.href === pathname)?.label ?? "ATLAS";
}
