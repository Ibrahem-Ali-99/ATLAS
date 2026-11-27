import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  CircleGauge,
  Clock3,
  CloudOff,
  Database,
  Filter,
  HardDrive,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Terminal,
  Webhook,
  WifiOff,
  Workflow,
  X,
  XCircle,
} from "lucide-react";
import { Badge, Button, type Tone } from "./components";

type Severity = "Info" | "Warning" | "Critical";
type EventStatus = "Resolved" | "Open" | "Failed" | "Running";
type OperationalEvent = {
  id: string;
  title: string;
  source: string;
  severity: Severity;
  status: EventStatus;
  timestamp: string;
  correlation: string;
  error?: string;
  retryable?: boolean;
  restricted?: boolean;
};

const initialEvents: OperationalEvent[] = [
  { id: "EVT-2048", title: "Campaign delivery adapter unavailable", source: "Campaign worker", severity: "Warning", status: "Open", timestamp: "10:42 AM", correlation: "corr_7fa2c1", error: "No delivery provider is configured for this workspace." },
  { id: "EVT-2047", title: "Account enrichment job failed", source: "Research worker", severity: "Critical", status: "Failed", timestamp: "9:18 AM", correlation: "corr_62bd90", error: "The sandbox enrichment adapter returned an unavailable response.", retryable: true },
  { id: "EVT-2046", title: "Knowledge indexing completed", source: "Indexing worker", severity: "Info", status: "Resolved", timestamp: "8:54 AM", correlation: "corr_18ac42" },
  { id: "EVT-2045", title: "Workflow waiting for approval", source: "Automation worker", severity: "Info", status: "Running", timestamp: "Yesterday", correlation: "corr_a922de" },
  { id: "EVT-2044", title: "Restricted audit event", source: "Security service", severity: "Warning", status: "Resolved", timestamp: "Yesterday", correlation: "corr_private", restricted: true },
];

const severityTone = (severity: Severity): Tone => severity === "Info" ? "blue" : severity === "Warning" ? "amber" : "red";
const statusTone = (status: EventStatus): Tone => status === "Resolved" ? "green" : status === "Running" ? "blue" : status === "Open" ? "amber" : "red";

export function MonitoringWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [events, setEvents] = useState(initialEvents);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("All severities");
  const [status, setStatus] = useState("All statuses");
  const [date, setDate] = useState("Last 24 hours");
  const [selected, setSelected] = useState<OperationalEvent | null>(null);
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const filtered = useMemo(() => events.filter((event) =>
    `${event.title} ${event.source} ${event.correlation}`.toLowerCase().includes(search.toLowerCase()) &&
    (severity === "All severities" || event.severity === severity) &&
    (status === "All statuses" || event.status === status),
  ), [events, search, severity, status]);
  const updateFilter = (setter: (value: string) => void, value: string) => {
    setter(value);
    setLoading(true);
    window.setTimeout(() => setLoading(false), 350);
  };
  const retry = () => {
    if (!selected?.retryable) return;
    setRetrying(true);
    window.setTimeout(() => {
      const updated = { ...selected, status: "Running" as EventStatus, timestamp: "Just now", error: undefined, retryable: false };
      setEvents((current) => current.map((event) => event.id === selected.id ? updated : event));
      setSelected(updated);
      setRetrying(false);
      onToast("Sandbox job retry started");
    }, 600);
  };
  return (
    <main className="module-main monitoring-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Workspace operations</div><h1>Monitoring</h1><p>Inspect prototype service health, workers, integrations, and operational events.</p></div><Badge tone="amber"><AlertTriangle size={13} /> 2 degraded</Badge></div>
      <section className="health-grid" aria-label="System health">
        <HealthCard icon={Server} name="ATLAS application" detail="Frontend workspace" state="Healthy" tone="green" />
        <HealthCard icon={Workflow} name="Automation worker" detail="Sandbox execution only" state="Healthy" tone="green" />
        <HealthCard icon={HardDrive} name="Knowledge indexer" detail="1 processing job" state="Degraded" tone="amber" />
        <HealthCard icon={CloudOff} name="Delivery services" detail="No provider connected" state="Unavailable" tone="red" />
      </section>
      <div className="monitoring-grid">
        <section className="panel worker-panel"><div className="panel-header"><div><h2>Background workers</h2><p>Local prototype worker status</p></div></div><div className="service-list"><ServiceRow icon={Bot} name="Agent runner" detail="1 active · 4 completed today" status="Healthy" tone="green" /><ServiceRow icon={Workflow} name="Workflow runner" detail="1 waiting for approval" status="Healthy" tone="green" /><ServiceRow icon={Database} name="Knowledge indexer" detail="1 processing · 1 failed" status="Degraded" tone="amber" /><ServiceRow icon={Webhook} name="Campaign delivery" detail="Provider not configured" status="Unavailable" tone="red" /></div></section>
        <section className="panel integration-panel"><div className="panel-header"><div><h2>Integration status</h2><p>Configured prototype adapters</p></div></div><div className="service-list"><ServiceRow icon={Database} name="CRM records" detail="Local prototype state" status="Sandbox" tone="purple" /><ServiceRow icon={Webhook} name="External project channel" detail="Not connected" status="Unavailable" tone="red" /><ServiceRow icon={ShieldCheck} name="Audit records" detail="Restricted access" status="Healthy" tone="green" restricted /></div></section>
      </div>
      <section className="panel events-panel">
        <div className="panel-header"><div><h2>Operational events</h2><p>Search warnings, failures, and execution results</p></div></div>
        <div className="event-filters"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search events or correlation IDs" aria-label="Search operational events" /></label><select value={severity} onChange={(event) => updateFilter(setSeverity, event.target.value)} aria-label="Filter event severity"><option>All severities</option><option>Info</option><option>Warning</option><option>Critical</option></select><select value={status} onChange={(event) => updateFilter(setStatus, event.target.value)} aria-label="Filter event status"><option>All statuses</option><option>Resolved</option><option>Open</option><option>Failed</option><option>Running</option></select><select value={date} onChange={(event) => updateFilter(setDate, event.target.value)} aria-label="Filter event date"><option>Last 24 hours</option><option>Last 7 days</option><option>Last 30 days</option></select></div>
        {loading ? <div className="module-empty compact" role="status"><LoaderCircle className="spinning" size={21} /><strong>Updating events</strong><p>Applying operational filters…</p></div> : <div className="events-table" role="table" aria-label="Operational events"><div className="event-row head" role="row"><span>Event</span><span>Source</span><span>Severity</span><span>Status</span><span>Timestamp</span><span>Correlation ID</span><span /></div>{filtered.length ? filtered.map((event) => <button className="event-row" role="row" key={event.id} onClick={() => setSelected(event)}><span className="operation-primary"><span className="operation-icon"><Activity size={15} /></span><span><strong>{event.title}</strong><small>{event.id}</small></span></span><span>{event.source}</span><span><Badge tone={severityTone(event.severity)}>{event.severity}</Badge></span><span><Badge tone={statusTone(event.status)}>{event.status}</Badge></span><span>{event.timestamp}</span><code>{event.correlation}</code><ChevronRight size={14} /></button>) : <div className="module-empty"><CircleGauge size={25} /><strong>No events found</strong><p>Change the search or filters to see other operational events.</p><Button size="sm" onClick={() => { setSearch(""); setSeverity("All severities"); setStatus("All statuses"); }}>Clear filters</Button></div>}</div>}
      </section>

      {selected && <><button className="drawer-backdrop" aria-label="Close event details" onClick={() => setSelected(null)} /><aside className="drawer operations-drawer monitoring-drawer" aria-label={`${selected.title} event details`}><div className="drawer-header"><div><h2>{selected.title}</h2><p>{selected.id} · {selected.source}</p></div><Button size="icon" variant="ghost" aria-label="Close event details" onClick={() => setSelected(null)}><X size={17} /></Button></div><div className="drawer-content"><div className="detail-status"><span><Badge tone={severityTone(selected.severity)}>{selected.severity}</Badge> <Badge tone={statusTone(selected.status)}>{selected.status}</Badge></span><span>{selected.timestamp}</span></div>{selected.restricted && <div className="permission-state"><LockKeyhole size={17} /><span><strong>Restricted event</strong><small>Detailed audit payloads require security administrator access.</small></span></div>}<div className="sandbox-callout"><Terminal size={16} /><span><strong>Prototype environment</strong><small>These operational records describe local simulated services, not production infrastructure.</small></span></div><section className="run-section"><h3>Event timeline</h3><div className="run-timeline"><EventStep title="Job queued" detail="Worker accepted the local job" /><EventStep title="Execution started" detail={selected.timestamp} />{selected.status === "Failed" ? <EventStep title="Execution failed" detail={selected.error || "Unknown failure"} failed /> : <EventStep title="Result recorded" detail={`Status: ${selected.status}`} />}</div></section><section className="run-section"><h3>Execution result</h3>{selected.error ? <div className="state-banner error"><CircleAlert size={16} /><span><strong>Error details</strong><small>{selected.error}</small></span></div> : <div className="execution-result"><CheckCircle2 size={17} /><span><strong>Result recorded</strong><small>The worker completed its local prototype step.</small></span></div>}</section><section className="run-section"><h3>Correlation</h3><div className="correlation-card"><code>{selected.correlation}</code><span>Use this identifier to trace related prototype events.</span></div></section></div><div className="drawer-footer"><Button disabled={!selected.retryable || retrying} onClick={retry}>{retrying ? <LoaderCircle size={14} /> : <RefreshCw size={14} />} Retry job</Button><Button variant="primary" onClick={() => onToast("Correlation identifier copied")}>Copy correlation ID</Button></div></aside></>}
    </main>
  );
}

function HealthCard({ icon: Icon, name, detail, state, tone }: { icon: typeof Server; name: string; detail: string; state: string; tone: Tone }) {
  return <article className="panel health-card"><span className={`health-icon badge-${tone}`}><Icon size={17} /></span><div><strong>{name}</strong><small>{detail}</small></div><Badge tone={tone}>{state}</Badge></article>;
}
function ServiceRow({ icon: Icon, name, detail, status, tone, restricted }: { icon: typeof Server; name: string; detail: string; status: string; tone: Tone; restricted?: boolean }) {
  return <div className="service-row"><span><Icon size={15} /></span><div><strong>{name}</strong><small>{detail}</small></div>{restricted && <LockKeyhole size={13} />}<Badge tone={tone}>{status}</Badge></div>;
}
function EventStep({ title, detail, failed }: { title: string; detail: string; failed?: boolean }) {
  return <div className={`run-step ${failed ? "failed" : "complete"}`}><span>{failed ? <XCircle size={14} /> : <Check size={14} />}</span><div><strong>{title}</strong><small>{detail}</small></div>{failed ? <AlertTriangle size={14} /> : <Check size={14} />}</div>;
}
