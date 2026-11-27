import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  BadgeCheck,
  ArrowRight,
  Bell,
  BookOpen,
  Bot,
  Blocks,
  BriefcaseBusiness,
  Building2,
  Check,
  CheckCircle2,
  ChartNoAxesCombined,
  ChevronDown,
  ChevronRight,
  CircleGauge,
  Command,
  CreditCard,
  Filter,
  Inbox,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
  Megaphone,
  Menu,
  MessageSquareText,
  Moon,
  MoreHorizontal,
  Plus,
  Search,
  Settings,
  Sparkles,
  Sun,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { Avatar, Badge, Button, MetricCard, Modal, type Tone } from "./components";
import type { CRMSection } from "./crm";
import { appConfig } from "./appConfig";
import type { AuthView } from "./auth";

const CRMWorkspace = lazy(() => import("./crm").then((module) => ({ default: module.CRMWorkspace })));
const InboxWorkspace = lazy(() => import("./inbox").then((module) => ({ default: module.InboxWorkspace })));
const AssistantWorkspace = lazy(() => import("./assistant").then((module) => ({ default: module.AssistantWorkspace })));
const KnowledgeWorkspace = lazy(() => import("./knowledge").then((module) => ({ default: module.KnowledgeWorkspace })));
const ApprovalsWorkspace = lazy(() => import("./approvals").then((module) => ({ default: module.ApprovalsWorkspace })));
const AgentRunsWorkspace = lazy(() => import("./agentRuns").then((module) => ({ default: module.AgentRunsWorkspace })));
const WorkflowsWorkspace = lazy(() => import("./workflows").then((module) => ({ default: module.WorkflowsWorkspace })));
const AnalyticsWorkspace = lazy(() => import("./analytics").then((module) => ({ default: module.AnalyticsWorkspace })));
const CampaignsWorkspace = lazy(() => import("./campaigns").then((module) => ({ default: module.CampaignsWorkspace })));
const MonitoringWorkspace = lazy(() => import("./monitoring").then((module) => ({ default: module.MonitoringWorkspace })));
const AuthWorkspace = lazy(() => import("./auth").then((module) => ({ default: module.AuthWorkspace })));
const SettingsWorkspace = lazy(() => import("./settings").then((module) => ({ default: module.SettingsWorkspace })));
const IntegrationsWorkspace = lazy(() => import("./integrations").then((module) => ({ default: module.IntegrationsWorkspace })));
const BillingWorkspace = lazy(() => import("./billing").then((module) => ({ default: module.BillingWorkspace })));

const navigation = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "CRM", icon: Users },
  { label: "Inbox", icon: Inbox, count: 16 },
  { label: "Assistant", icon: Bot },
  { label: "Knowledge", icon: BookOpen },
  { label: "Approvals", icon: BadgeCheck, count: 2 },
  { label: "Workflows", icon: Workflow },
  { label: "Agent Runs", icon: Activity, count: 1 },
  { label: "Analytics", icon: ChartNoAxesCombined },
  { label: "Campaigns", icon: Megaphone },
  { label: "Monitoring", icon: CircleGauge },
  { label: "Integrations", icon: Blocks },
  { label: "Billing", icon: CreditCard },
  { label: "Settings", icon: Settings },
];

const destinationDescriptions: Record<string, string> = {
  Inbox: "Manage customer messages, assignments, and response queues.",
  Assistant: "Coordinate research, drafting, and guided workspace actions.",
  Knowledge: "Organize trusted company resources and shared documentation.",
  Approvals: "Review requests, supporting context, and approval history.",
  Workflows: "Configure repeatable processes and monitor active automations.",
  "Agent Runs": "Inspect agent execution timelines, evidence, approvals, and results.",
  Analytics: "Explore operational performance and customer activity.",
  Campaigns: "Plan and coordinate targeted customer communications.",
  Monitoring: "Track workspace health, events, and operational alerts.",
  Integrations: "Connect ATLAS with the tools used across your organization.",
  Billing: "Review workspace plan state, usage availability, and billing access.",
  Settings: "Manage organization preferences, members, security, and access.",
};

const pipeline = [
  { label: "New", value: 7, tone: "blue" as Tone, width: "100%" },
  { label: "Contacted", value: 1, tone: "purple" as Tone, width: "14%" },
  { label: "Qualified", value: 5, tone: "amber" as Tone, width: "71%" },
  { label: "Won", value: 1, tone: "green" as Tone, width: "14%" },
  { label: "Lost", value: 1, tone: "red" as Tone, width: "14%" },
];

const activities = [
  {
    id: 1,
    company: "Arcade",
    initials: "AR",
    text: "New inquiry received",
    detail: "Enterprise plan · Website",
    time: "8 min ago",
    tone: "blue" as Tone,
  },
  {
    id: 2,
    company: "Layers",
    initials: "LY",
    text: "Opportunity moved to Qualified",
    detail: "Assigned to Olivia Martin",
    time: "42 min ago",
    tone: "purple" as Tone,
  },
  {
    id: 3,
    company: "Northstar",
    initials: "NS",
    text: "Approval requested",
    detail: "Custom terms review",
    time: "1 hr ago",
    tone: "amber" as Tone,
  },
  {
    id: 4,
    company: "Vertex",
    initials: "VX",
    text: "Email reply received",
    detail: "Re: Security questionnaire",
    time: "3 hr ago",
    tone: "green" as Tone,
  },
];

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [activeNav, setActiveNav] = useState("Overview");
  const [profileOpen, setProfileOpen] = useState(false);
  const [orgOpen, setOrgOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedActivity, setSelectedActivity] = useState<(typeof activities)[number] | null>(null);
  const [drilldown, setDrilldown] = useState<string | null>(null);
  const [pipelineStage, setPipelineStage] = useState("All stages");
  const [search, setSearch] = useState("");
  const [opportunityName, setOpportunityName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [approved, setApproved] = useState<number[]>([]);
  const [crmSection, setCrmSection] = useState<CRMSection>("Companies");
  const [reviewingApproval, setReviewingApproval] = useState<number | null>(null);
  const [authView, setAuthView] = useState<AuthView | null>(null);
  const [authBanner, setAuthBanner] = useState("");

  useEffect(() => {
    const stored = localStorage.getItem("atlas-theme");
    const nextTheme =
      stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches)
        ? "dark"
        : "light";
    setTheme(nextTheme);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("atlas-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    document.querySelector(".main-column")?.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [activeNav]);

  const filteredActivities = useMemo(
    () =>
      activities.filter((item) =>
        `${item.company} ${item.text} ${item.detail}`.toLowerCase().includes(search.toLowerCase()),
      ),
    [search],
  );

  function createOpportunity() {
    setCreateOpen(false);
    setToast(`${opportunityName} was added to New`);
    setOpportunityName("");
    setCompanyName("");
  }

  function navigate(label: string) {
    setActiveNav(label);
    setSidebarOpen(false);
    setProfileOpen(false);
    setOrgOpen(false);
  }

  if (authView) {
    return <Suspense fallback={<main className="module-loading" role="status"><LoaderCircle size={20} /><span>Loading account…</span></main>}><AuthWorkspace initialView={authView} theme={theme} banner={authBanner} onThemeChange={() => setTheme(theme === "light" ? "dark" : "light")} onComplete={(message) => { setAuthView(null); setAuthBanner(""); setToast(message); navigate("Overview"); }} /></Suspense>;
  }

  return (
    <div className="app-shell">
      {sidebarOpen && (
        <button
          className="mobile-backdrop"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside className={`sidebar ${collapsed ? "sidebar-collapsed" : ""} ${sidebarOpen ? "sidebar-mobile-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark" aria-hidden="true">
            A
          </div>
          {!collapsed && <span className="brand-name">ATLAS</span>}
          <Button
            variant="ghost"
            size="icon"
            className="sidebar-close"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={18} />
          </Button>
        </div>

        <div className="org-wrap">
          <button className="org-switcher" onClick={() => setOrgOpen(!orgOpen)} aria-expanded={orgOpen}>
            <span className="org-logo">{appConfig.organization.initials}</span>
            {!collapsed && (
              <>
                <span className="org-copy">
                  <strong>{appConfig.organization.name}</strong>
                  <small>{appConfig.organization.descriptor}</small>
                </span>
                <ChevronDown size={15} />
              </>
            )}
          </button>
          {orgOpen && !collapsed && (
            <div className="menu org-menu">
              <p className="menu-label">Workspaces</p>
              <button><span className="org-logo">{appConfig.organization.initials}</span><span>{appConfig.organization.name}<small>Current organization</small></span><Check size={15} /></button>
              <button disabled title="No additional organizations are available"><span className="org-logo muted-logo">—</span><span>Another organization<small>No access granted</small></span></button>
              <div className="menu-separator" />
              <button onClick={() => { setAuthBanner(""); setAuthView("setup"); }}><Plus size={16} /><span>Create workspace</span></button>
            </div>
          )}
        </div>

        <nav className="sidebar-nav" aria-label="Primary navigation">
          {navigation.map(({ label, icon: Icon, count }, index) => (
            <div key={label}>
              {index === 0 && !collapsed && <p className="nav-section">Work</p>}
              {label === "Monitoring" && !collapsed && <p className="nav-section">Manage</p>}
              <button
                className={`nav-item ${activeNav === label ? "nav-item-active" : ""}`}
                aria-current={activeNav === label ? "page" : undefined}
                title={collapsed ? label : undefined}
                onClick={() => {
                  navigate(label);
                }}
              >
                <Icon size={17} strokeWidth={1.8} />
                {!collapsed && <span>{label}</span>}
                {!collapsed && count !== undefined && (
                  <span className="nav-count">{label === "Approvals" ? Math.max(0, count - approved.length) : count}</span>
                )}
              </button>
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="collapse-button" onClick={() => setCollapsed(!collapsed)}>
            <ChevronRight size={16} className={collapsed ? "" : "rotate-180"} />
            {!collapsed && <span>Collapse sidebar</span>}
          </button>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <Button className="mobile-menu" variant="ghost" size="icon" aria-label="Open navigation" onClick={() => { setCollapsed(false); setSidebarOpen(true); }}>
              <Menu size={19} />
            </Button>
            <div className="breadcrumbs" aria-label="Breadcrumb">
              <span>{appConfig.organization.name}</span>
              <ChevronRight size={13} />
              <strong>{activeNav}</strong>
              {activeNav === "CRM" && <><ChevronRight size={13} /><strong>{crmSection}</strong></>}
            </div>
          </div>
          <div className="topbar-actions">
            <button className="command-search" onClick={() => setToast("Command palette opened")}>
              <Search size={15} />
              <span>Search workspace</span>
              <kbd><Command size={11} /> K</kbd>
            </button>
            <Button variant="ghost" size="icon" aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`} onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
              {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
            </Button>
            <Button variant="ghost" size="icon" aria-label="Notifications" className="notification-button">
              <Bell size={17} />
              <span />
            </Button>
            <div className="profile-wrap">
              <button className="profile-button" aria-label="Open profile menu" aria-expanded={profileOpen} onClick={() => setProfileOpen(!profileOpen)}>
                <Avatar initials={appConfig.user.initials} tone="blue" size="sm" />
                <ChevronDown size={13} />
              </button>
              {profileOpen && (
                <div className="menu profile-menu">
                  <div className="profile-summary"><Avatar initials={appConfig.user.initials} tone="blue" /><span><strong>{appConfig.user.name}</strong><small>{appConfig.user.email}</small></span></div>
                  <div className="menu-separator" />
                  <button onClick={() => navigate("Settings")}><Users size={16} /><span>Profile & preferences</span></button>
                  <button onClick={() => navigate("Settings")}><Settings size={16} /><span>Workspace settings</span></button>
                  <div className="menu-separator" />
                  <button onClick={() => { setProfileOpen(false); setAuthBanner(""); setAuthView("login"); }}><span>Sign out</span></button>
                </div>
              )}
            </div>
          </div>
        </header>

        <Suspense fallback={<main className="module-loading" role="status"><LoaderCircle size={20} /><span>Loading workspace…</span></main>}>
        {activeNav === "Overview" ? <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="live-dot" /> Live workspace</div>
              <h1>Good morning, {appConfig.user.firstName}</h1>
              <p>Here’s what needs your attention across {appConfig.organization.name}.</p>
            </div>
            <div className="page-actions">
              <Button variant="secondary" onClick={() => setFilterOpen(true)}><Filter size={15} /> Filters</Button>
              <Button variant="primary" onClick={() => setCreateOpen(true)}><Plus size={16} /> New opportunity</Button>
            </div>
          </div>

          <section className="metric-grid" aria-label="Workspace metrics">
            <MetricCard label="Companies" value="4" meta="Total accounts" icon={Building2} onClick={() => setDrilldown("Companies")} />
            <MetricCard label="Active leads" value="13" meta="15 total leads" icon={BriefcaseBusiness} onClick={() => setDrilldown("Active leads")} />
            <MetricCard label="Open inquiries" value="16" meta="Awaiting response" icon={MessageSquareText} onClick={() => setDrilldown("Open inquiries")} />
            <MetricCard label="Pending approvals" value={`${Math.max(0, 2 - approved.length)}`} meta="Needs review" icon={BadgeCheck} onClick={() => setDrilldown("Pending approvals")} />
          </section>

          <div className="overview-grid">
            <section className="panel pipeline-panel">
              <div className="panel-header">
                <div>
                  <h2>Lead pipeline</h2>
                  <p>15 leads across five stages</p>
                </div>
                <button className="text-button" onClick={() => { setCrmSection("Opportunities"); setActiveNav("CRM"); }}>View pipeline <ArrowRight size={14} /></button>
              </div>
              <div className="pipeline-list">
                {pipeline.map((stage) => (
                  <button
                    className={`pipeline-row ${pipelineStage === stage.label ? "pipeline-row-active" : ""}`}
                    key={stage.label}
                    onClick={() => setPipelineStage(stage.label)}
                  >
                    <span className={`status-dot dot-${stage.tone}`} />
                    <span className="pipeline-label">{stage.label}</span>
                    <div className="bar-track"><span className={`bar-fill fill-${stage.tone}`} style={{ width: stage.width }} /></div>
                    <strong>{stage.value}</strong>
                    <ChevronRight size={14} />
                  </button>
                ))}
              </div>
            </section>

            <section className="panel attention-panel">
              <div className="panel-header">
                <div>
                  <h2>Needs attention</h2>
                  <p>Priority items for today</p>
                </div>
                <Badge tone="amber">{Math.max(0, 2 - approved.length)} pending</Badge>
              </div>
              <div className="approval-list">
                {approved.length < 2 ? (
                  [1, 2].filter((id) => !approved.includes(id)).map((id) => (
                    <article className="approval-item" key={id}>
                      <div className="approval-icon"><AlertCircle size={16} /></div>
                      <div>
                        <h3>{id === 1 ? "Custom terms review" : "Campaign audience approval"}</h3>
                        <p>{id === 1 ? "Northstar · Enterprise agreement" : "Q2 customer nurture · 15 leads"}</p>
                        <div className="approval-actions">
                          <Button size="sm" variant="primary" onClick={() => setReviewingApproval(id)}>Review and approve</Button>
                          <Button size="sm" variant="secondary" onClick={() => setReviewingApproval(id)}>View details</Button>
                        </div>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="empty-state"><CheckCircle2 size={22} /><strong>All caught up</strong><p>There are no approvals waiting for review.</p></div>
                )}
              </div>
            </section>
          </div>

          <section className="panel activity-panel">
            <div className="panel-header activity-header">
              <div>
                <h2>Recent customer activity</h2>
                <p>Latest updates across your accounts</p>
              </div>
              <div className="table-tools">
                <label className="small-search">
                  <Search size={14} />
                  <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search activity" aria-label="Search activity" />
                  {search && <button aria-label="Clear search" onClick={() => setSearch("")}><X size={13} /></button>}
                </label>
                <Button variant="secondary" size="sm" onClick={() => setFilterOpen(true)}><ListFilter size={14} /> Filter</Button>
              </div>
            </div>
            <div className="activity-table" role="table" aria-label="Recent customer activity">
              <div className="activity-row table-head" role="row">
                <span>Company</span><span>Activity</span><span>Time</span><span />
              </div>
              {filteredActivities.length ? filteredActivities.map((item) => (
                <button className="activity-row" role="row" key={item.id} onClick={() => setSelectedActivity(item)}>
                  <span className="company-cell"><Avatar initials={item.initials} tone={item.tone} /><strong>{item.company}</strong></span>
                  <span className="activity-copy"><strong>{item.text}</strong><small>{item.detail}</small></span>
                  <span className="time-cell">{item.time}</span>
                  <MoreHorizontal size={17} />
                </button>
              )) : (
                <div className="empty-state table-empty"><Search size={22} /><strong>No activity found</strong><p>Try changing your search or filters.</p><Button size="sm" onClick={() => setSearch("")}>Clear search</Button></div>
              )}
            </div>
          </section>
        </main> : activeNav === "CRM" ? (
          <CRMWorkspace section={crmSection} onSectionChange={setCrmSection} onToast={setToast} />
        ) : activeNav === "Inbox" ? (
          <InboxWorkspace onToast={setToast} />
        ) : activeNav === "Assistant" ? (
          <AssistantWorkspace onToast={setToast} />
        ) : activeNav === "Knowledge" ? (
          <KnowledgeWorkspace onToast={setToast} />
        ) : activeNav === "Approvals" ? (
          <ApprovalsWorkspace onToast={setToast} />
        ) : activeNav === "Workflows" ? (
          <WorkflowsWorkspace onToast={setToast} />
        ) : activeNav === "Agent Runs" ? (
          <AgentRunsWorkspace onToast={setToast} />
        ) : activeNav === "Analytics" ? (
          <AnalyticsWorkspace onToast={setToast} />
        ) : activeNav === "Campaigns" ? (
          <CampaignsWorkspace onToast={setToast} />
        ) : activeNav === "Monitoring" ? (
          <MonitoringWorkspace onToast={setToast} />
        ) : activeNav === "Integrations" ? (
          <IntegrationsWorkspace onToast={setToast} />
        ) : activeNav === "Billing" ? (
          <BillingWorkspace onToast={setToast} />
        ) : activeNav === "Settings" ? (
          <SettingsWorkspace onToast={setToast} onSessionExpired={() => { setAuthBanner("Your local session ended. Sign in again to continue."); setAuthView("login"); }} />
        ) : (
          <main className="placeholder-page">
            <div className="placeholder-icon">{(() => { const ItemIcon = navigation.find((item) => item.label === activeNav)?.icon || Sparkles; return <ItemIcon size={21} />; })()}</div>
            <h1>{activeNav}</h1>
            <p>{destinationDescriptions[activeNav]}</p>
            <Button onClick={() => setActiveNav("Overview")}>Return to Overview</Button>
          </main>
        )}
        </Suspense>
      </div>

      {filterOpen && (
        <>
          <button className="drawer-backdrop" aria-label="Close filters" onClick={() => setFilterOpen(false)} />
          <aside className="drawer" aria-label="Advanced filters">
            <div className="drawer-header"><div><h2>Advanced filters</h2><p>Refine the overview data.</p></div><Button variant="ghost" size="icon" onClick={() => setFilterOpen(false)} aria-label="Close filters"><X size={17} /></Button></div>
            <div className="drawer-content">
              <label className="field"><span>Pipeline stage</span><select value={pipelineStage} onChange={(e) => setPipelineStage(e.target.value)}><option>All stages</option>{pipeline.map((stage) => <option key={stage.label}>{stage.label}</option>)}</select></label>
              <label className="field"><span>Owner</span><select><option>All owners</option><option>Olivia Martin</option><option>Sam Rivera</option></select></label>
              <label className="field"><span>Activity period</span><select><option>Last 7 days</option><option>Today</option><option>Last 30 days</option></select></label>
              <div className="filter-checks"><span>Include</span><label><input type="checkbox" defaultChecked /> Open inquiries</label><label><input type="checkbox" defaultChecked /> Pending approvals</label><label><input type="checkbox" /> Closed leads</label></div>
            </div>
            <div className="drawer-footer"><Button variant="ghost" onClick={() => setPipelineStage("All stages")}>Reset</Button><Button variant="primary" onClick={() => { setFilterOpen(false); setToast("Filters applied"); }}>Apply filters</Button></div>
          </aside>
        </>
      )}

      {selectedActivity && (
        <>
          <button className="drawer-backdrop" aria-label="Close activity" onClick={() => setSelectedActivity(null)} />
          <aside className="drawer" aria-label="Activity details">
            <div className="drawer-header"><div className="drawer-title-with-avatar"><Avatar initials={selectedActivity.initials} tone={selectedActivity.tone} /><div><h2>{selectedActivity.company}</h2><p>Customer activity</p></div></div><Button variant="ghost" size="icon" onClick={() => setSelectedActivity(null)} aria-label="Close activity"><X size={17} /></Button></div>
            <div className="drawer-content">
              <div className="detail-status"><Badge tone={selectedActivity.tone}>Recent activity</Badge><span>{selectedActivity.time}</span></div>
              <h3 className="detail-title">{selectedActivity.text}</h3>
              <p className="detail-copy">{selectedActivity.detail}. This event was captured automatically in the customer timeline and is visible to the account team.</p>
              <div className="detail-card"><span>Owner</span><strong><Avatar initials={appConfig.user.initials} tone="blue" size="sm" /> {appConfig.user.name}</strong></div>
              <div className="detail-card"><span>Source</span><strong><Activity size={15} /> Customer timeline</strong></div>
            </div>
            <div className="drawer-footer"><Button variant="secondary" onClick={() => setSelectedActivity(null)}>Close</Button><Button variant="primary" onClick={() => setToast("Opening customer record")}>Open customer <ArrowRight size={14} /></Button></div>
          </aside>
        </>
      )}

      <Modal open={createOpen} title="New opportunity" description="Add a qualified opportunity to your CRM." onClose={() => setCreateOpen(false)}>
        <div className="dialog-body">
          <label className="field"><span>Opportunity name</span><input autoFocus value={opportunityName} onChange={(e) => setOpportunityName(e.target.value)} placeholder="e.g. Enterprise expansion" /></label>
          <label className="field"><span>Company</span><input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Search or enter a company" /></label>
          <div className="field-row">
            <label className="field"><span>Stage</span><select defaultValue="New"><option>New</option><option>Contacted</option><option>Qualified</option></select></label>
            <label className="field"><span>Owner</span><select><option>Olivia Martin</option><option>Sam Rivera</option></select></label>
          </div>
        </div>
        <div className="dialog-footer"><Button variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button><Button variant="primary" disabled={!opportunityName.trim() || !companyName.trim()} onClick={createOpportunity}>Create opportunity</Button></div>
      </Modal>

      <Modal open={!!drilldown} title={drilldown || ""} description="Workspace detail view" onClose={() => setDrilldown(null)}>
        <div className="drilldown-list">
          {drilldown === "Pending approvals" ? (
            [1, 2].map((id) => <div className="drilldown-item" key={id}><span className="approval-icon"><BadgeCheck size={15} /></span><span><strong>{id === 1 ? "Custom terms review" : "Campaign audience approval"}</strong><small>{id === 1 ? "Northstar" : "Q2 customer nurture"}</small></span><Badge tone="amber">Pending</Badge></div>)
          ) : (
            activities.slice(0, drilldown === "Companies" ? 4 : 3).map((item) => <button className="drilldown-item" key={item.id} onClick={() => { setDrilldown(null); setSelectedActivity(item); }}><Avatar initials={item.initials} tone={item.tone} size="sm" /><span><strong>{item.company}</strong><small>{item.detail}</small></span><ChevronRight size={15} /></button>)
          )}
        </div>
        <div className="dialog-footer"><Button variant="secondary" onClick={() => setDrilldown(null)}>Close</Button><Button variant="primary" onClick={() => { setDrilldown(null); setToast("Opening detailed workspace view"); }}>View all <ArrowRight size={14} /></Button></div>
      </Modal>

      <Modal
        open={reviewingApproval !== null}
        title={reviewingApproval === 1 ? "Custom terms review" : "Campaign audience approval"}
        description="Review the request details before confirming approval."
        onClose={() => setReviewingApproval(null)}
      >
        <div className="approval-review">
          <div className="review-callout"><AlertCircle size={17} /><span><strong>Review required</strong><p>Confirm the scope, requester, and linked record below. Approval cannot be completed from the overview card.</p></span></div>
          <dl>
            <div><dt>Requested by</dt><dd>{reviewingApproval === 1 ? "Nadia Flores · Northstar" : `Sam Rivera · ${appConfig.organization.name}`}</dd></div>
            <div><dt>Request</dt><dd>{reviewingApproval === 1 ? "Enterprise agreement custom terms" : "Q2 nurture audience · 15 leads"}</dd></div>
            <div><dt>Owner</dt><dd>Olivia Martin</dd></div>
          </dl>
        </div>
        <div className="dialog-footer">
          <Button onClick={() => setReviewingApproval(null)}>Cancel</Button>
          <Button variant="primary" onClick={() => {
            if (reviewingApproval !== null) setApproved([...approved, reviewingApproval]);
            setReviewingApproval(null);
            setToast("Approval completed after review");
          }}><Check size={14} /> Confirm approval</Button>
        </div>
      </Modal>

      {toast && <div className="toast" role="status"><CheckCircle2 size={16} />{toast}</div>}
    </div>
  );
}

export default App;
