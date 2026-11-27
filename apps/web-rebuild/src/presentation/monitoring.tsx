import { useEffect, useMemo, useState } from "react";
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
import { failureMessage, loadDiagnostics } from "@/data/resources";
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


const severityTone = (severity: Severity): Tone => severity === "Info" ? "blue" : severity === "Warning" ? "amber" : "red";
const statusTone = (status: EventStatus): Tone => status === "Resolved" ? "green" : status === "Running" ? "blue" : status === "Open" ? "amber" : "red";

export function MonitoringWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [events, setEvents] = useState<OperationalEvent[]>([]);
  const [knowledge, setKnowledge] = useState("Checking");
  const [workers, setWorkers] = useState("Checking");
  const [integrations, setIntegrations] = useState<{ name: string; detail: string; status: string }[]>([]);
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
  useEffect(() => {
    loadDiagnostics().then((diagnostics) => {
      const failed = diagnostics.failed_runs.map((item) => ({ id: item.id, title: item.error_code || "Agent run failed", source: "Agent runner", severity: "Critical" as Severity, status: "Failed" as EventStatus, timestamp: "Recorded", correlation: item.id.slice(0, 8), error: item.hint || item.error_code || "Run failed" }));
      const integrationEvents = diagnostics.integration_failures.map((item) => ({ id: item.id, title: item.error || "Integration failure", source: "Integration", severity: "Warning" as Severity, status: "Open" as EventStatus, timestamp: "Recorded", correlation: item.id.slice(0, 8), error: item.hint || item.error || item.status }));
      setEvents([...failed, ...integrationEvents]);
      setKnowledge(diagnostics.activity ? `${diagnostics.activity.knowledge.ready} ready · ${diagnostics.activity.knowledge.indexing} indexing · ${diagnostics.activity.knowledge.failed} failed` : "No knowledge activity");
      setWorkers(diagnostics.activity ? `${diagnostics.activity.workflows.running} running · ${diagnostics.activity.workflows.needs_attention} waiting · ${diagnostics.activity.workflows.failed} failed` : `${diagnostics.workers.length} workers`);
      setIntegrations((diagnostics.activity?.integrations || []).map((item) => ({ name: item.provider || item.type, detail: item.health || item.status, status: item.status })));
    }).catch((error: unknown) => onToast(failureMessage(error)));
  }, [onToast]);
  const updateFilter = (setter: (value: string) => void, value: string) => setter(value);
  const copyCorrelation = (value: string) => {
    void navigator.clipboard.writeText(value).then(() => onToast("Correlation identifier copied")).catch(() => onToast("The identifier could not be copied"));
  };
  return (
    <main className="module-main monitoring-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Workspace operations</div><h1>Monitoring</h1><p>Inspect recorded service health, workers, integrations, and operational events.</p></div><Badge tone="amber"><AlertTriangle size={13} /> {events.length} recorded</Badge></div>
      <section className="health-grid" aria-label="System health">
        <HealthCard icon={Server} name="ATLAS application" detail="Harbor review workspace" state="Healthy" tone="green" />
        <HealthCard icon={Workflow} name="Automation worker" detail={workers} state="Recorded" tone="blue" />
        <HealthCard icon={HardDrive} name="Knowledge indexer" detail={knowledge} state="Recorded" tone="amber" />
        <HealthCard icon={CloudOff} name="Delivery services" detail="Live customer delivery disabled" state="Restricted" tone="red" />
      </section>
      <div className="monitoring-grid">
        <section className="panel worker-panel"><div className="panel-header"><div><h2>Background workers</h2><p>Recorded worker status</p></div></div><div className="service-list"><ServiceRow icon={Bot} name="Agent runner" detail={workers} status="Recorded" tone="blue" /><ServiceRow icon={Database} name="Knowledge indexer" detail={knowledge} status="Recorded" tone="amber" /></div></section>
        <section className="panel integration-panel"><div className="panel-header"><div><h2>Integration status</h2><p>Stored provider verification</p></div></div><div className="service-list">{integrations.length ? integrations.map((item) => <ServiceRow key={item.name} icon={Webhook} name={item.name} detail={item.detail} status={item.status} tone="blue" />) : <ServiceRow icon={Webhook} name="No integration activity" detail="Diagnostics did not return provider rows" status="Recorded" tone="neutral" />}</div></section>
      </div>
      <section className="panel events-panel">
        <div className="panel-header"><div><h2>Operational events</h2><p>Search warnings, failures, and execution results</p></div></div>
        <div className="event-filters"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search events or correlation IDs" aria-label="Search operational events" /></label><select value={severity} onChange={(event) => updateFilter(setSeverity, event.target.value)} aria-label="Filter event severity"><option>All severities</option><option>Info</option><option>Warning</option><option>Critical</option></select><select value={status} onChange={(event) => updateFilter(setStatus, event.target.value)} aria-label="Filter event status"><option>All statuses</option><option>Resolved</option><option>Open</option><option>Failed</option><option>Running</option></select><select value={date} disabled aria-label="Event dates are not included in diagnostics" title="Diagnostics do not include event times"><option>Recorded events</option></select></div>
        {loading ? <div className="module-empty compact" role="status"><LoaderCircle className="spinning" size={21} /><strong>Updating events</strong><p>Applying operational filters…</p></div> : <div className="events-table" role="table" aria-label="Operational events"><div className="event-row head" role="row"><span>Event</span><span>Source</span><span>Severity</span><span>Status</span><span>Timestamp</span><span>Correlation ID</span><span /></div>{filtered.length ? filtered.map((event) => <button className="event-row" role="row" key={event.id} onClick={() => setSelected(event)}><span className="operation-primary"><span className="operation-icon"><Activity size={15} /></span><span><strong>{event.title}</strong><small>{event.id}</small></span></span><span>{event.source}</span><span><Badge tone={severityTone(event.severity)}>{event.severity}</Badge></span><span><Badge tone={statusTone(event.status)}>{event.status}</Badge></span><span>{event.timestamp}</span><code>{event.correlation}</code><ChevronRight size={14} /></button>) : <div className="module-empty"><CircleGauge size={25} /><strong>No events found</strong><p>Change the search or filters to see other operational events.</p><Button size="sm" onClick={() => { setSearch(""); setSeverity("All severities"); setStatus("All statuses"); }}>Clear filters</Button></div>}</div>}
      </section>

      {selected && <><button className="drawer-backdrop" aria-label="Close event details" onClick={() => setSelected(null)} /><aside className="drawer operations-drawer monitoring-drawer" aria-label={`${selected.title} event details`}><div className="drawer-header"><div><h2>{selected.title}</h2><p>{selected.id} · {selected.source}</p></div><Button size="icon" variant="ghost" aria-label="Close event details" onClick={() => setSelected(null)}><X size={17} /></Button></div><div className="drawer-content"><div className="detail-status"><span><Badge tone={severityTone(selected.severity)}>{selected.severity}</Badge> <Badge tone={statusTone(selected.status)}>{selected.status}</Badge></span><span>{selected.timestamp}</span></div>{selected.restricted && <div className="permission-state"><LockKeyhole size={17} /><span><strong>Restricted event</strong><small>Detailed audit payloads require security administrator access.</small></span></div>}<div className="sandbox-callout"><Terminal size={16} /><span><strong>Prototype environment</strong><small>These operational records describe local simulated services, not production infrastructure.</small></span></div><section className="run-section"><h3>Recorded result</h3><div className="run-timeline">{selected.error ? <EventStep title={selected.title} detail={selected.error} failed /> : <EventStep title={selected.status} detail={selected.timestamp} />}</div></section><section className="run-section"><h3>Execution result</h3>{selected.error ? <div className="state-banner error"><CircleAlert size={16} /><span><strong>Error details</strong><small>{selected.error}</small></span></div> : <div className="execution-result"><CheckCircle2 size={17} /><span><strong>Result recorded</strong><small>The worker completed its local prototype step.</small></span></div>}</section><section className="run-section"><h3>Correlation</h3><div className="correlation-card"><code>{selected.correlation}</code><span>Use this identifier to trace related prototype events.</span></div></section></div><div className="drawer-footer"><Button disabled title="Retry the failed record from its own module">Retry unavailable</Button><Button variant="primary" onClick={() => copyCorrelation(selected.id)}>Copy correlation ID</Button></div></aside></>}
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
