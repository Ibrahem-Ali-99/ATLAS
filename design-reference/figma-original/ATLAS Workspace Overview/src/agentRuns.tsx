import { useMemo, useState } from "react";
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

const initialRuns: AgentRun[] = [
  { id: "RUN-1048", name: "Qualify new Arcade inquiry", agent: "Lead qualification agent", status: "Waiting approval", started: "8 min ago", duration: "42 sec", linked: "Arcade · Mina Park" },
  { id: "RUN-1047", name: "Prepare Northstar follow-up", agent: "Inbox response agent", status: "Completed", started: "52 min ago", duration: "31 sec", linked: "Northstar · Nadia Flores" },
  { id: "RUN-1046", name: "Enrich Vertex account", agent: "Account research agent", status: "Failed", started: "3 hr ago", duration: "18 sec", linked: "Vertex", retryable: true },
  { id: "RUN-1045", name: "Review inactive leads", agent: "Lead hygiene agent", status: "Cancelled", started: "Yesterday", duration: "12 sec", linked: "Layers · 3 leads" },
  { id: "RUN-1044", name: "Create onboarding tasks", agent: "Opportunity agent", status: "Running", started: "Just now", duration: "9 sec", linked: "Arcade pilot" },
];

const toneFor = (status: RunStatus): Tone =>
  status === "Completed" ? "green" : status === "Running" ? "blue" : status === "Waiting approval" ? "amber" : "red";

export function AgentRunsWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [runs, setRuns] = useState(initialRuns);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [selected, setSelected] = useState<AgentRun | null>(null);
  const [retrying, setRetrying] = useState(false);
  const filtered = useMemo(() => runs.filter((run) =>
    `${run.name} ${run.agent} ${run.linked}`.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || run.status === status),
  ), [runs, search, status]);
  const retry = () => {
    if (!selected?.retryable) return;
    setRetrying(true);
    window.setTimeout(() => {
      const updated = { ...selected, status: "Running" as RunStatus, started: "Just now", duration: "2 sec" };
      setRuns((current) => current.map((run) => run.id === selected.id ? updated : run));
      setSelected(updated);
      setRetrying(false);
      onToast("Agent run restarted in sandbox");
    }, 650);
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
          <div className="sandbox-callout"><Terminal size={16} /><span><strong>Sandbox execution</strong><small>This run uses local prototype state and does not deliver changes to external systems.</small></span></div>
          <section className="run-section"><h3>Execution timeline</h3><div className="run-timeline">
            <RunStep icon={Play} title="Run started" detail="Trigger: New customer inquiry" state="complete" />
            <RunStep icon={Database} title="CRM context retrieved" detail={`Linked record: ${selected.linked}`} state="complete" />
            <RunStep icon={FileSearch} title="Knowledge evidence retrieved" detail="2 trusted passages used" state="complete" />
            <RunStep icon={Wrench} title="Tool call prepared" detail="crm.tasks.create · Sandbox" state={selected.status === "Failed" ? "failed" : "complete"} />
            <RunStep icon={ShieldCheck} title="Approval checkpoint" detail={selected.status === "Waiting approval" ? "Waiting for reviewer" : "Review completed"} state={selected.status === "Waiting approval" ? "waiting" : selected.status === "Failed" ? "skipped" : "complete"} />
          </div></section>
          <section className="run-section"><h3>Tool calls</h3><div className="tool-call"><div><Wrench size={14} /><strong>crm.tasks.create</strong><Badge tone={selected.status === "Failed" ? "red" : "green"}>{selected.status === "Failed" ? "Failed" : "Prepared"}</Badge></div><pre>{`{\n  "mode": "sandbox",\n  "record": "${selected.linked}"\n}`}</pre></div></section>
          <section className="run-section"><h3>Retrieved evidence</h3><div className="evidence-list"><div><Building2 size={14} /><span><strong>CRM record</strong><small>{selected.linked}</small></span></div><div><FileSearch size={14} /><span><strong>Knowledge passage</strong><small>Customer follow-up playbook · Section 3</small></span></div></div></section>
          <section className="run-section"><h3>Proposed action</h3><div className="proposed-change"><Target size={17} /><div><strong>Create a linked follow-up task</strong><p>Requires approval before execution.</p></div></div></section>
          {selected.status === "Failed" && <div className="state-banner error"><CircleAlert size={16} /><span><strong>Tool call failed</strong><small>The sandbox CRM adapter reported that the linked record was unavailable.</small></span></div>}
          {selected.status === "Completed" && <div className="execution-result"><CheckCircle2 size={17} /><span><strong>Run completed</strong><small>All sandbox steps completed and the reviewed result was recorded.</small></span></div>}
          {selected.status === "Waiting approval" && <div className="state-banner warning"><ShieldCheck size={16} /><span><strong>Approval required</strong><small>The proposed action will not continue until a reviewer decides.</small></span><Button size="sm" onClick={() => onToast("Opening linked approval")}>Open approval <ArrowRight size={13} /></Button></div>}
          {selected.status === "Cancelled" && <div className="execution-result rejected"><XCircle size={17} /><span><strong>Run cancelled</strong><small>No action was executed.</small></span></div>}
        </div>
        <div className="drawer-footer"><Button disabled={!selected.retryable || retrying} onClick={retry}>{retrying ? <LoaderCircle size={14} /> : <RefreshCw size={14} />} Retry run</Button><Button variant="primary" onClick={() => onToast("Run log copied")}>Copy run log</Button></div>
      </aside></>}
    </main>
  );
}

function RunStep({ icon: Icon, title, detail, state }: { icon: typeof Play; title: string; detail: string; state: "complete" | "waiting" | "failed" | "skipped" }) {
  return <div className={`run-step ${state}`}><span><Icon size={14} /></span><div><strong>{title}</strong><small>{detail}</small></div>{state === "complete" ? <Check size={14} /> : state === "failed" ? <AlertTriangle size={14} /> : state === "waiting" ? <Clock3 size={14} /> : <X size={14} />}</div>;
}
