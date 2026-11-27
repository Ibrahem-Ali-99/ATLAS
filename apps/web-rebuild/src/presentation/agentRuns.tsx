import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Building2,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  Database,
  FileSearch,
  Filter,
  History,
  LoaderCircle,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Target,
  Terminal,
  Wrench,
  X,
  XCircle,
} from "lucide-react";
import { failureMessage, getRun, listRuns, relativeTime, resumeRun } from "@/data/resources";
import { Badge, Button, type Tone } from "./components";

type RunStatus = "Running" | "Completed" | "Waiting approval" | "Failed" | "Cancelled";
type AgentRun = {
  id: string;
  name: string;
  agent: string;
  status: RunStatus;
  started: string;
  duration: string;
  linked: string;
  retryable?: boolean;
};

const statusLabel = (value: string): RunStatus => value === "awaiting_approval" ? "Waiting approval" : value === "completed" ? "Completed" : value === "failed" ? "Failed" : value === "running" ? "Running" : "Cancelled";

const toneFor = (status: RunStatus): Tone =>
  status === "Completed" ? "green" : status === "Running" ? "blue" : status === "Waiting approval" ? "amber" : "red";

export function AgentRunsWorkspace({ onToast, onOpenApprovals }: { onToast: (message: string) => void; onOpenApprovals?: () => void }) {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [selected, setSelected] = useState<AgentRun | null>(null);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof getRun>> | null>(null);
  const [retrying, setRetrying] = useState(false);
  const filtered = useMemo(() => runs.filter((run) =>
    `${run.name} ${run.agent} ${run.linked}`.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || run.status === status),
  ), [runs, search, status]);
  useEffect(() => {
    listRuns().then((rows) => setRuns(rows.map((row) => ({ id: row.id, name: row.inquiry_subject || "Agent run", agent: "Qualification agent", status: statusLabel(row.status), started: relativeTime(row.started_at), duration: row.finished_at ? "Finished" : "In progress", linked: row.inquiry_subject || "Inquiry", retryable: row.status === "failed" })))).catch((error: unknown) => onToast(failureMessage(error)));
  }, [onToast]);
  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    getRun(selected.id).then(setDetail).catch(() => setDetail(null));
  }, [selected]);
  const retry = () => {
    if (!selected?.retryable) return;
    setRetrying(true);
    void resumeRun(selected.id).then(() => getRun(selected.id)).then((detail) => {
      const updated = { ...selected, status: statusLabel(detail.run.status), started: "Just now" };
      setRuns((current) => current.map((run) => run.id === selected.id ? updated : run));
      setSelected(updated);
      onToast("Agent run resume was recorded");
    }).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setRetrying(false));
  };
  return (
    <main className="module-main operations-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Agent execution history</div><h1>Agent Runs</h1><p>Inspect agent activity, evidence, approvals, tool calls, and execution results.</p></div><Badge tone="blue">{runs.filter((run) => run.status === "Running").length} running</Badge></div>
      <section className="panel operations-panel">
        <div className="operations-toolbar"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search agent runs" aria-label="Search agent runs" />{search && <button onClick={() => setSearch("")} aria-label="Clear search"><X size={14} /></button>}</label><label className="toolbar-select"><Filter size={14} /><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter run status"><option>All statuses</option><option>Running</option><option>Completed</option><option>Waiting approval</option><option>Failed</option><option>Cancelled</option></select></label></div>
        <div className="operations-table runs-table" role="table" aria-label="Agent run history">
          <div className="operations-row head" role="row"><span>Run</span><span>Agent</span><span>Status</span><span>Started</span><span>Duration</span><span>Linked records</span><span /></div>
          {filtered.length ? filtered.map((run) => <button className="operations-row" role="row" key={run.id} onClick={() => setSelected(run)}>
            <span className="operation-primary"><span className="operation-icon"><Bot size={15} /></span><span><strong>{run.name}</strong><small>{run.id}</small></span></span><span>{run.agent}</span><span><Badge tone={toneFor(run.status)}>{run.status}</Badge></span><span>{run.started}</span><span>{run.duration}</span><span>{run.linked}</span><ChevronRight size={15} />
          </button>) : <div className="module-empty"><History size={25} /><strong>No agent runs found</strong><p>Change the search or status filter to view other runs.</p><Button size="sm" onClick={() => { setSearch(""); setStatus("All statuses"); }}>Clear filters</Button></div>}
        </div>
      </section>

      {selected && <><button className="drawer-backdrop" aria-label="Close run details" onClick={() => setSelected(null)} /><aside className="drawer operations-drawer run-drawer" aria-label={`${selected.name} run details`}>
        <div className="drawer-header"><div><h2>{selected.name}</h2><p>{selected.id} · {selected.agent}</p></div><Button size="icon" variant="ghost" aria-label="Close run details" onClick={() => setSelected(null)}><X size={17} /></Button></div>
        <div className="drawer-content">
          <div className="detail-status"><Badge tone={toneFor(selected.status)}>{selected.status}</Badge><span>{selected.started} · {selected.duration}</span></div>
          <div className="sandbox-callout"><Terminal size={16} /><span><strong>Stored execution</strong><small>Steps and approvals below are the records saved for this run. External delivery stays behind an approval.</small></span></div>
          <section className="run-section"><h3>Execution timeline</h3>{detail?.events.length ? <div className="run-timeline">{detail.events.map((event) => <RunStep key={`${event.step}-${event.created_at}`} icon={event.status === "failed" ? AlertTriangle : Play} title={event.step} detail={event.error_message || event.status} state={event.status === "failed" ? "failed" : "complete"} />)}</div> : <p className="detail-copy">No execution steps are stored for this run.</p>}</section>
          <section className="run-section"><h3>Approvals</h3>{detail?.approvals.length ? <div className="evidence-list">{detail.approvals.map((approval) => <div key={approval.id}><ShieldCheck size={14} /><span><strong>{approval.action_type.replaceAll("_", " ")}</strong><small>{approval.status}</small></span></div>)}</div> : <p className="detail-copy">No approval is linked to this run.</p>}</section>
          <section className="run-section"><h3>Linked record</h3><div className="evidence-list"><div><Building2 size={14} /><span><strong>{selected.linked}</strong><small>{detail?.run.error_message || selected.status}</small></span></div></div></section>
          {selected.status === "Failed" && <div className="state-banner error"><CircleAlert size={16} /><span><strong>Run failed</strong><small>{detail?.run.error_message || "The stored run did not finish."}</small></span></div>}
          {selected.status === "Completed" && <div className="execution-result"><CheckCircle2 size={17} /><span><strong>Run completed</strong><small>The stored run finished. External delivery stays behind an approval.</small></span></div>}
          {selected.status === "Waiting approval" && <div className="state-banner warning"><ShieldCheck size={16} /><span><strong>Approval required</strong><small>The proposed action will not continue until a reviewer decides.</small></span>{onOpenApprovals && <Button size="sm" onClick={onOpenApprovals}>Open approval <ArrowRight size={13} /></Button>}</div>}
          {selected.status === "Cancelled" && <div className="execution-result rejected"><XCircle size={17} /><span><strong>Run cancelled</strong><small>No action was executed.</small></span></div>}
        </div>
        <div className="drawer-footer"><Button disabled={!selected.retryable || retrying} onClick={retry}>{retrying ? <LoaderCircle size={14} /> : <RefreshCw size={14} />} Retry run</Button><Button variant="primary" onClick={() => { const text = (detail?.events || []).map((event) => `${event.created_at} ${event.step} ${event.status} ${event.error_message || ""}`).join("\n") || selected.id; void navigator.clipboard.writeText(text).then(() => onToast("Run log copied")).catch(() => onToast("The run log could not be copied")); }}>Copy run log</Button></div>
      </aside></>}
    </main>
  );
}

function RunStep({ icon: Icon, title, detail, state }: { icon: typeof Play; title: string; detail: string; state: "complete" | "waiting" | "failed" | "skipped" }) {
  return <div className={`run-step ${state}`}><span><Icon size={14} /></span><div><strong>{title}</strong><small>{detail}</small></div>{state === "complete" ? <Check size={14} /> : state === "failed" ? <AlertTriangle size={14} /> : state === "waiting" ? <Clock3 size={14} /> : <X size={14} />}</div>;
}
