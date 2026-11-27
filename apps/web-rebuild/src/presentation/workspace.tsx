"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BadgeCheck,
  Bell,
  Blocks,
  BookOpen,
  Bot,
  BriefcaseBusiness,
  Building2,
  ChartNoAxesCombined,
  Check,
  CheckCircle2,
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
  Sun,
  Users,
  Workflow,
  X,
} from "lucide-react";

import { searchRecords, loadOnboardingProgress, loadProviderStatus, type SearchHit } from "@/data/resources";
import { ApiError } from "@/data/client";
import { companyIdByName, createOpportunity, decideApproval, initials, loadNavCounts, loadOverview, type ActivityItem, type ApprovalItem, type NavCounts, type OverviewSnapshot } from "@/data/overview";
import { getSession, logout, type Session } from "@/data/session";
import { Avatar, Badge, Button, MetricCard, Modal } from "@/presentation/components";
import { SignIn } from "@/presentation/sign-in";
import { bindWorkspace } from "@/presentation/appConfig";
import { AgentRunsWorkspace } from "@/presentation/agentRuns";
import { AnalyticsWorkspace } from "@/presentation/analytics";
import { ApprovalsWorkspace } from "@/presentation/approvals";
import { AssistantWorkspace } from "@/presentation/assistant";
import { BillingWorkspace } from "@/presentation/billing";
import { CampaignsWorkspace } from "@/presentation/campaigns";
import { CRMWorkspace, type CRMSection } from "@/presentation/crm";
import { InboxWorkspace } from "@/presentation/inbox";
import { IntegrationsWorkspace } from "@/presentation/integrations";
import { KnowledgeWorkspace } from "@/presentation/knowledge";
import { MonitoringWorkspace } from "@/presentation/monitoring";
import { SettingsWorkspace } from "@/presentation/settings";
import { WorkflowsWorkspace } from "@/presentation/workflows";

const navigation = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "CRM", icon: Users },
  { label: "Inbox", icon: Inbox, count: "inbox" as const },
  { label: "Assistant", icon: Bot },
  { label: "Knowledge", icon: BookOpen },
  { label: "Approvals", icon: BadgeCheck, count: "approvals" as const },
  { label: "Workflows", icon: Workflow },
  { label: "Agent Runs", icon: Activity, count: "runs" as const },
  { label: "Analytics", icon: ChartNoAxesCombined },
  { label: "Campaigns", icon: Megaphone },
  { label: "Monitoring", icon: CircleGauge },
  { label: "Integrations", icon: Blocks },
  { label: "Billing", icon: CreditCard },
  { label: "Settings", icon: Settings },
];

const ORG_KEY = "atlas.rebuild.organization";

export function Workspace() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [organizationId, setOrganizationId] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem("atlas-theme");
    setTheme(stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light");
    getSession()
      .then((next) => {
        setSession(next);
        const saved = localStorage.getItem(ORG_KEY);
        const membership = next.memberships.find((item) => item.organization_id === saved) ?? next.memberships[0];
        setOrganizationId(membership?.organization_id ?? null);
      })
      .catch((error: unknown) => {
        if (!(error instanceof ApiError) || error.status !== 401) setReady(true);
      })
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("atlas-theme", theme);
  }, [theme]);

  if (!ready) {
    return <main className="module-loading" role="status"><LoaderCircle size={20} /><span>Loading account…</span></main>;
  }
  if (!session || !organizationId) {
    return (
      <SignIn
        theme={theme}
        onThemeChange={() => setTheme(theme === "light" ? "dark" : "light")}
        onComplete={(next) => {
          setSession(next);
          setOrganizationId(next.memberships[0]?.organization_id ?? null);
        }}
      />
    );
  }
  const membership = session.memberships.find((item) => item.organization_id === organizationId) ?? session.memberships[0];
  if (!membership) {
    return <SignIn theme={theme} onThemeChange={() => setTheme(theme === "light" ? "dark" : "light")} onComplete={setSession} />;
  }
  return (
    <Shell
      session={session}
      organizationId={membership.organization_id}
      organizationName={membership.organization_name}
      theme={theme}
      onThemeChange={() => setTheme(theme === "light" ? "dark" : "light")}
      onOrganization={(id) => {
        localStorage.setItem(ORG_KEY, id);
        setOrganizationId(id);
      }}
      onSignOut={() => {
        setSession(null);
        setOrganizationId(null);
      }}
    />
  );
}

function Shell({
  session,
  organizationId,
  organizationName,
  theme,
  onThemeChange,
  onOrganization,
  onSignOut,
}: {
  session: Session;
  organizationId: string;
  organizationName: string;
  theme: "light" | "dark";
  onThemeChange: () => void;
  onOrganization: (id: string) => void;
  onSignOut: () => void;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [activeNav, setActiveNav] = useState("Overview");
  const [profileOpen, setProfileOpen] = useState(false);
  const [orgOpen, setOrgOpen] = useState(false);
  const [counts, setCounts] = useState<NavCounts>({});
  const [crmSection, setCrmSection] = useState<CRMSection>("Companies");
  const [crmFocus, setCrmFocus] = useState("");
  const [inboxFocus, setInboxFocus] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const firstName = session.user.full_name.split(" ")[0] || session.user.full_name;
  const membership = session.memberships.find((item) => item.organization_id === organizationId);
  bindWorkspace({ organizationId, organizationName, userName: session.user.full_name, email: session.user.email, slug: membership?.organization_slug });
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    let cancelled = false;
    loadNavCounts(organizationId).then((next) => {
      if (!cancelled) setCounts(next);
    });
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  function navigate(label: string) {
    setActiveNav(label);
    setSidebarOpen(false);
    setProfileOpen(false);
    setOrgOpen(false);
    setSearchOpen(false);
  }

  function openCrm(section: CRMSection, query: string) {
    setCrmSection(section);
    setCrmFocus(query);
    navigate("CRM");
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "k" || !(event.metaKey || event.ctrlKey) || event.altKey) return;
      event.preventDefault();
      setSearchOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function signOut() {
    await logout().catch(() => undefined);
    onSignOut();
  }

  return (
    <div className="app-shell">
      {sidebarOpen && <button className="mobile-backdrop" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
      <aside className={`sidebar ${collapsed ? "sidebar-collapsed" : ""} ${sidebarOpen ? "sidebar-mobile-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark" aria-hidden="true">A</div>
          {!collapsed && <span className="brand-name">ATLAS</span>}
          <Button variant="ghost" size="icon" className="sidebar-close" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}><X size={18} /></Button>
        </div>
        <div className="org-wrap">
          <button className="org-switcher" onClick={() => setOrgOpen(!orgOpen)} aria-expanded={orgOpen} aria-label="Organization">
            <span className="org-logo">{initials(organizationName)}</span>
            {!collapsed && (
              <>
                <span className="org-copy"><strong>{organizationName}</strong><small>Primary organization</small></span>
                <ChevronDown size={15} />
              </>
            )}
          </button>
          {orgOpen && !collapsed && (
            <div className="menu org-menu">
              <p className="menu-label">Workspaces</p>
              {session.memberships.map((membership) => (
                <button key={membership.organization_id} onClick={() => { onOrganization(membership.organization_id); setOrgOpen(false); }}>
                  <span className="org-logo">{initials(membership.organization_name)}</span>
                  <span>{membership.organization_name}<small>{membership.organization_id === organizationId ? "Current organization" : membership.role}</small></span>
                  {membership.organization_id === organizationId ? <Check size={15} /> : null}
                </button>
              ))}
            </div>
          )}
        </div>
        <nav className="sidebar-nav" aria-label="Primary navigation">
          {navigation.map(({ label, icon: Icon, count }, index) => (
            <div key={label}>
              {index === 0 && !collapsed && <p className="nav-section">Work</p>}
              {label === "Monitoring" && !collapsed && <p className="nav-section">Manage</p>}
              <button className={`nav-item ${activeNav === label ? "nav-item-active" : ""}`} aria-current={activeNav === label ? "page" : undefined} title={collapsed ? label : undefined} onClick={() => navigate(label)}>
                <Icon size={17} strokeWidth={1.8} />
                {!collapsed && <span>{label}</span>}
                {!collapsed && count && counts[count] !== undefined && <span className="nav-count">{counts[count]}</span>}
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
              <span>{organizationName}</span>
              <ChevronRight size={13} />
              <strong>{activeNav}</strong>
            </div>
          </div>
          <div className="topbar-actions">
            <button className="command-search" aria-label="Search workspace" aria-keyshortcuts="Control+K" onClick={() => setSearchOpen(true)}>
              <Search size={15} />
              <span>Search workspace</span>
              <kbd><Command size={11} /> K</kbd>
            </button>
            <Button variant="ghost" size="icon" aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`} onClick={onThemeChange}>
              {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
            </Button>
            <Button variant="ghost" size="icon" aria-label="Open approvals" className="notification-button" onClick={() => navigate("Approvals")}>
              <Bell size={17} />
              {counts.approvals ? <span /> : null}
            </Button>
            <div className="profile-wrap">
              <button className="profile-button" aria-label="Open profile menu" aria-expanded={profileOpen} onClick={() => setProfileOpen(!profileOpen)}>
                <Avatar initials={initials(session.user.full_name)} tone="blue" size="sm" />
                <ChevronDown size={13} />
              </button>
              {profileOpen && (
                <div className="menu profile-menu">
                  <div className="profile-summary"><Avatar initials={initials(session.user.full_name)} tone="blue" /><span><strong>{session.user.full_name}</strong><small>{session.user.email}</small></span></div>
                  <div className="menu-separator" />
                  <button onClick={() => navigate("Settings")}><Users size={16} /><span>Profile & preferences</span></button>
                  <button onClick={() => navigate("Settings")}><Settings size={16} /><span>Workspace settings</span></button>
                  <div className="menu-separator" />
                  <button onClick={() => void signOut()}><span>Sign out</span></button>
                </div>
              )}
            </div>
          </div>
        </header>
        {activeNav === "Overview" ? <Overview organizationId={organizationId} organizationName={organizationName} firstName={firstName} onApproved={() => void loadNavCounts(organizationId).then(setCounts)} onOpenSetup={(section, crm) => { if (crm) openCrm(crm, ""); else navigate(section); }} /> : null}
        {activeNav === "CRM" ? <CRMWorkspace section={crmSection} onSectionChange={setCrmSection} onToast={setToast} focusQuery={crmFocus} onOpenInbox={() => navigate("Inbox")} /> : null}
        {activeNav === "Inbox" ? <InboxWorkspace onToast={setToast} onOpenCrm={openCrm} focusQuery={inboxFocus} /> : null}
        {activeNav === "Assistant" ? <AssistantWorkspace onToast={setToast} /> : null}
        {activeNav === "Knowledge" ? <KnowledgeWorkspace onToast={setToast} /> : null}
        {activeNav === "Approvals" ? <ApprovalsWorkspace onToast={setToast} onOpenCrm={(query) => openCrm("Companies", query)} /> : null}
        {activeNav === "Workflows" ? <WorkflowsWorkspace onToast={setToast} /> : null}
        {activeNav === "Agent Runs" ? <AgentRunsWorkspace onToast={setToast} onOpenApprovals={() => navigate("Approvals")} onOpenInbox={(query) => { setInboxFocus(query); navigate("Inbox"); }} /> : null}
        {activeNav === "Analytics" ? <AnalyticsWorkspace onToast={setToast} onOpenCrm={() => navigate("CRM")} /> : null}
        {activeNav === "Campaigns" ? <CampaignsWorkspace onToast={setToast} /> : null}
        {activeNav === "Monitoring" ? <MonitoringWorkspace onToast={setToast} /> : null}
        {activeNav === "Integrations" ? <IntegrationsWorkspace onToast={setToast} /> : null}
        {activeNav === "Billing" ? <BillingWorkspace onToast={setToast} /> : null}
        {activeNav === "Settings" ? <SettingsWorkspace onToast={setToast} onSessionExpired={() => void signOut()} /> : null}
        {toast ? <div className="toast" role="status"><CheckCircle2 size={16} />{toast}</div> : null}
        <WorkspaceSearch open={searchOpen} onClose={() => setSearchOpen(false)} onNavigate={navigate} onRecord={openCrm} />
      </div>
    </div>
  );
}

function SetupChecklist({ onOpen }: { onOpen: (section: string, crm?: CRMSection) => void }) {
  const [progress, setProgress] = useState<Record<string, boolean> | null>(null);
  const [providersReady, setProvidersReady] = useState(false);
  useEffect(() => {
    loadOnboardingProgress().then(setProgress).catch(() => setProgress(null));
    loadProviderStatus().then((status) => setProvidersReady(Boolean(status.llm_ready && status.embedding_ready))).catch(() => setProvidersReady(false));
  }, []);
  if (!progress) return null;
  const items: { key: string; title: string; section: string; crm?: CRMSection }[] = [
    { key: "profile", title: "Save the organization profile", section: "Settings" },
    { key: "company", title: "Add the first company", section: "CRM", crm: "Companies" },
    { key: "contact", title: "Add the first contact", section: "CRM", crm: "Contacts" },
    { key: "lead", title: "Create the first lead", section: "CRM", crm: "Leads" },
    { key: "inquiry", title: "Record the first customer inquiry", section: "CRM", crm: "Customer inquiries" },
    { key: "workflow", title: "Complete a workflow run", section: "Workflows" },
    { key: "knowledge", title: "Index the first document", section: "Knowledge" },
    { key: "assistant", title: providersReady ? "Verify an answer with citations" : "Configure chat and embeddings", section: providersReady ? "Assistant" : "Integrations" },
  ];
  const completed = items.filter((item) => progress[item.key]).length;
  return <section className="panel" aria-labelledby="setup-checklist"><div className="panel-header"><div><h2 id="setup-checklist">Setup checklist</h2><p role="status">{completed} of {items.length} steps completed</p></div></div><div className="pipeline-list">{items.map((item) => <button className="pipeline-row" key={item.key} onClick={() => onOpen(item.section, item.crm)}><span className={`status-dot ${progress[item.key] ? "dot-green" : "dot-amber"}`} /><span className="pipeline-label">{item.title}</span><strong>{progress[item.key] ? "Done" : "Open"}</strong><ChevronRight size={14} /></button>)}</div></section>;
}

function WorkspaceSearch({ open, onClose, onNavigate, onRecord }: { open: boolean; onClose: () => void; onNavigate: (label: string) => void; onRecord: (section: CRMSection, query: string) => void }) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) { setQuery(""); setHits([]); setError(""); }
  }, [open]);
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) { setHits([]); return; }
    const timer = window.setTimeout(() => {
      searchRecords(trimmed).then((next) => { setHits(next); setError(""); }).catch(() => setError("Record search failed."));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const pages = navigation.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase()));
  return <Modal open={open} title="Search workspace" description="Find a page or a company, contact, or lead." onClose={onClose}>
    <div className="dialog-body">
      <label className="field"><span>Search</span><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Pages and records" aria-label="Search workspace records" /></label>
      <div className="command-results">
        {pages.map((item) => <button key={item.label} onClick={() => onNavigate(item.label)}><strong>{item.label}</strong><small>Page</small></button>)}
        {hits.map((hit) => <button key={`${hit.kind}-${hit.id}`} onClick={() => onRecord(hit.kind, hit.label)}><strong>{hit.label}</strong><small>{hit.kind}</small></button>)}
        {error ? <p className="detail-copy">{error}</p> : null}
        {query.trim().length >= 2 && !hits.length && !error ? <p className="detail-copy">No matching records.</p> : null}
      </div>
    </div>
  </Modal>;
}

function Overview({
  organizationId,
  organizationName,
  firstName,
  onApproved,
  onOpenSetup,
}: {
  organizationId: string;
  organizationName: string;
  firstName: string;
  onApproved: () => void;
  onOpenSetup: (section: string, crm?: CRMSection) => void;
}) {
  const [period, setPeriod] = useState("30d");
  const [data, setData] = useState<OverviewSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterOpen, setFilterOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedActivity, setSelectedActivity] = useState<ActivityItem | null>(null);
  const [drilldown, setDrilldown] = useState<string | null>(null);
  const [pipelineStage, setPipelineStage] = useState("All stages");
  const [search, setSearch] = useState("");
  const [opportunityName, setOpportunityName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [stage, setStage] = useState("new");
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<ApprovalItem | null>(null);
  const [reviewError, setReviewError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadOverview(organizationId, period)
      .then((next) => {
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiError ? caught.message : "The overview could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId, period, revision]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const activities = data?.activities ?? [];
  const filteredActivities = useMemo(
    () => activities.filter((item) => `${item.company} ${item.text} ${item.detail}`.toLowerCase().includes(search.toLowerCase())),
    [activities, search],
  );

  async function saveOpportunity() {
    setFormError("");
    setSaving(true);
    try {
      const companyId = await companyIdByName(organizationId, companyName);
      if (!companyId) {
        setFormError("Enter a company that already exists in this workspace.");
        return;
      }
      await createOpportunity(organizationId, opportunityName.trim(), companyId, stage);
      setCreateOpen(false);
      setOpportunityName("");
      setCompanyName("");
      setStage("new");
      setToast(`${opportunityName.trim()} was added`);
      setRevision((value) => value + 1);
    } catch (caught) {
      setFormError(caught instanceof ApiError ? caught.message : "The opportunity was not created.");
    } finally {
      setSaving(false);
    }
  }

  async function confirmApproval() {
    if (!reviewing) return;
    setReviewError("");
    setSaving(true);
    try {
      await decideApproval(organizationId, reviewing.id);
      setReviewing(null);
      setToast("Approval completed after review");
      setRevision((value) => value + 1);
      onApproved();
    } catch (caught) {
      setReviewError(caught instanceof ApiError ? caught.message : "The approval was not recorded.");
    } finally {
      setSaving(false);
    }
  }

  if (loading && !data) {
    return <main className="module-loading" role="status"><LoaderCircle size={20} /><span>Loading workspace…</span></main>;
  }
  if (error && !data) {
    return <main><div className="empty-state"><AlertCircle size={22} /><strong>Overview unavailable</strong><p>{error}</p></div></main>;
  }
  if (!data) return null;

  return (
    <>
      <main>
        <div className="page-heading">
          <div>
            <div className="eyebrow"><span className="live-dot" /> Live workspace</div>
            <h1>Good morning, {firstName}</h1>
            <p>Here’s what needs your attention across {organizationName}.</p>
          </div>
          <div className="page-actions">
            <Button variant="secondary" onClick={() => setFilterOpen(true)}><Filter size={15} /> Filters</Button>
            <Button variant="primary" onClick={() => { setFormError(""); setCreateOpen(true); }}><Plus size={16} /> New opportunity</Button>
          </div>
        </div>
        <section className="metric-grid" aria-label="Workspace metrics">
          <MetricCard label="Companies" value={String(data.companies)} meta="Total accounts" icon={Building2} onClick={() => setDrilldown("Companies")} />
          <MetricCard label="Active leads" value={String(data.activeLeads)} meta={`${data.leadsTotal} total leads`} icon={BriefcaseBusiness} onClick={() => setDrilldown("Active leads")} />
          <MetricCard label="Open inquiries" value={String(data.openInquiries)} meta="Awaiting response" icon={MessageSquareText} onClick={() => setDrilldown("Open inquiries")} />
          <MetricCard label="Pending approvals" value={String(data.pendingApprovals)} meta="Needs review" icon={BadgeCheck} onClick={() => setDrilldown("Pending approvals")} />
        </section>
        <SetupChecklist onOpen={onOpenSetup} />
        <div className="overview-grid">
          <section className="panel pipeline-panel">
            <div className="panel-header">
              <div>
                <h2>Lead pipeline</h2>
                <p>{data.leadsTotal} leads across five stages</p>
              </div>
              <button className="text-button" onClick={() => setDrilldown("Active leads")}>View pipeline <ArrowRight size={14} /></button>
            </div>
            <div className="pipeline-list">
              {data.pipeline.map((item) => (
                <button className={`pipeline-row ${pipelineStage === item.label ? "pipeline-row-active" : ""}`} key={item.label} onClick={() => setPipelineStage(item.label)}>
                  <span className={`status-dot dot-${item.tone}`} />
                  <span className="pipeline-label">{item.label}</span>
                  <div className="bar-track"><span className={`bar-fill fill-${item.tone}`} style={{ width: item.width }} /></div>
                  <strong>{item.value}</strong>
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
              <Badge tone="amber">{data.approvals.length} pending</Badge>
            </div>
            <div className="approval-list">
              {data.approvals.length ? data.approvals.map((approval) => (
                <article className="approval-item" key={approval.id}>
                  <div className="approval-icon"><AlertCircle size={16} /></div>
                  <div>
                    <h3>{approval.title}</h3>
                    <p>{approval.detail}</p>
                    <div className="approval-actions">
                      <Button size="sm" variant="primary" onClick={() => { setReviewError(""); setReviewing(approval); }}>Review and approve</Button>
                      <Button size="sm" variant="secondary" onClick={() => { setReviewError(""); setReviewing(approval); }}>View details</Button>
                    </div>
                  </div>
                </article>
              )) : (
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
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search activity" aria-label="Search activity" />
                {search && <button aria-label="Clear search" onClick={() => setSearch("")}><X size={13} /></button>}
              </label>
              <Button variant="secondary" size="sm" onClick={() => setFilterOpen(true)}><ListFilter size={14} /> Filter</Button>
            </div>
          </div>
          <div className="activity-table" role="table" aria-label="Recent customer activity">
            <div className="activity-row table-head" role="row"><span>Company</span><span>Activity</span><span>Time</span><span /></div>
            {filteredActivities.length ? filteredActivities.map((item) => (
              <button className="activity-row" role="row" key={item.id} onClick={() => setSelectedActivity(item)}>
                <span className="company-cell"><Avatar initials={item.initials} tone={item.tone} /><strong>{item.company}</strong></span>
                <span className="activity-copy"><strong>{item.text}</strong><small>{item.detail}</small></span>
                <span className="time-cell">{item.time}</span>
                <MoreHorizontal size={17} />
              </button>
            )) : (
              <div className="empty-state table-empty"><Search size={22} /><strong>No activity found</strong><p>Try changing your search or filters.</p>{search ? <Button size="sm" onClick={() => setSearch("")}>Clear search</Button> : null}</div>
            )}
          </div>
        </section>
      </main>
      {filterOpen && (
        <>
          <button className="drawer-backdrop" aria-label="Close filters" onClick={() => setFilterOpen(false)} />
          <aside className="drawer" aria-label="Advanced filters">
            <div className="drawer-header"><div><h2>Advanced filters</h2><p>Refine the overview data.</p></div><Button variant="ghost" size="icon" onClick={() => setFilterOpen(false)} aria-label="Close filters"><X size={17} /></Button></div>
            <div className="drawer-content">
              <label className="field"><span>Pipeline stage</span><select value={pipelineStage} onChange={(event) => setPipelineStage(event.target.value)}><option>All stages</option>{data.pipeline.map((item) => <option key={item.label}>{item.label}</option>)}</select></label>
              <label className="field"><span>Activity period</span>
                <select value={period} onChange={(event) => setPeriod(event.target.value)}>
                  <option value="7d">Last 7 days</option>
                  <option value="30d">Last 30 days</option>
                  <option value="90d">Last 90 days</option>
                </select>
              </label>
            </div>
            <div className="drawer-footer"><Button variant="ghost" onClick={() => { setPipelineStage("All stages"); setPeriod("30d"); }}>Reset</Button><Button variant="primary" onClick={() => setFilterOpen(false)}>Apply filters</Button></div>
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
              <p className="detail-copy">{selectedActivity.detail}</p>
            </div>
            <div className="drawer-footer"><Button variant="secondary" onClick={() => setSelectedActivity(null)}>Close</Button></div>
          </aside>
        </>
      )}
      <Modal open={createOpen} title="New opportunity" description="Add a qualified opportunity to your CRM." onClose={() => setCreateOpen(false)}>
        <div className="dialog-body">
          <label className="field"><span>Opportunity name</span><input autoFocus value={opportunityName} onChange={(event) => setOpportunityName(event.target.value)} placeholder="e.g. Enterprise expansion" /></label>
          <label className="field"><span>Company</span><input value={companyName} onChange={(event) => setCompanyName(event.target.value)} placeholder="Enter a company in this workspace" list="overview-companies" /></label>
          <datalist id="overview-companies">{data.companyNames.map((name, index) => <option key={`${name}-${index}`} value={name} />)}</datalist>
          <div className="field-row">
            <label className="field"><span>Stage</span><select value={stage} onChange={(event) => setStage(event.target.value)}><option value="new">New</option><option value="contacted">Contacted</option><option value="qualified">Qualified</option></select></label>
          </div>
          {formError ? <div className="auth-error" role="alert"><AlertCircle size={15} />{formError}</div> : null}
        </div>
        <div className="dialog-footer">
          <Button variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="primary" disabled={!opportunityName.trim() || !companyName.trim() || saving} onClick={() => void saveOpportunity()}>{saving ? "Creating…" : "Create opportunity"}</Button>
        </div>
      </Modal>
      <Modal open={!!drilldown} title={drilldown || ""} description="Workspace detail view" onClose={() => setDrilldown(null)}>
        <div className="drilldown-list">
          {drilldown === "Pending approvals" ? (
            data.approvals.map((item) => <div className="drilldown-item" key={item.id}><span className="approval-icon"><BadgeCheck size={15} /></span><span><strong>{item.title}</strong><small>{item.detail}</small></span><Badge tone="amber">Pending</Badge></div>)
          ) : drilldown === "Companies" ? (
            data.companyNames.map((name, index) => <div className="drilldown-item" key={`${name}-${index}`}><Avatar initials={initials(name)} tone="blue" size="sm" /><span><strong>{name}</strong><small>Company</small></span></div>)
          ) : (
            filteredActivities.slice(0, 6).map((item) => <button className="drilldown-item" key={item.id} onClick={() => { setDrilldown(null); setSelectedActivity(item); }}><Avatar initials={item.initials} tone={item.tone} size="sm" /><span><strong>{item.company}</strong><small>{item.detail}</small></span><ChevronRight size={15} /></button>)
          )}
        </div>
        <div className="dialog-footer"><Button variant="secondary" onClick={() => setDrilldown(null)}>Close</Button></div>
      </Modal>
      <Modal open={reviewing !== null} title={reviewing?.title ?? ""} description="Review the request details before confirming approval." onClose={() => { if (!saving) setReviewing(null); }}>
        <div className="approval-review">
          <div className="review-callout"><AlertCircle size={17} /><span><strong>Review required</strong><p>Confirm the stored request before it can run.</p></span></div>
          <dl>
            <div><dt>Request</dt><dd>{reviewing?.request}</dd></div>
            <div><dt>Record</dt><dd>{reviewing?.detail}</dd></div>
          </dl>
          {reviewError ? <div className="auth-error" role="alert"><AlertCircle size={15} />{reviewError}</div> : null}
        </div>
        <div className="dialog-footer">
          <Button onClick={() => setReviewing(null)} disabled={saving}>Cancel</Button>
          <Button variant="primary" disabled={saving} onClick={() => void confirmApproval()}><Check size={14} /> {saving ? "Confirming…" : "Confirm approval"}</Button>
        </div>
      </Modal>
      {toast && <div className="toast" role="status"><CheckCircle2 size={16} />{toast}</div>}
    </>
  );
}
