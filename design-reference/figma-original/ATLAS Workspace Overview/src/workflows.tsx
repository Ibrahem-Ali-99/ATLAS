import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  Copy,
  Edit3,
  Filter,
  GitBranch,
  History,
  Link2Off,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  Save,
  Search,
  Settings2,
  Sparkles,
  Terminal,
  Trash2,
  Webhook,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import { Badge, Button, Modal, type Tone } from "./components";

type WorkflowStatus = "Active" | "Paused" | "Draft" | "Error";
type Trigger = "Record created" | "Status changed" | "Schedule" | "Inbox message";
type WorkflowDefinition = {
  id: number;
  name: string;
  description: string;
  status: WorkflowStatus;
  trigger: Trigger;
  updated: string;
  runs: number;
  owner: string;
  integrationError?: boolean;
  restricted?: boolean;
};

const initialWorkflows: WorkflowDefinition[] = [
  { id: 1, name: "Qualify new customer inquiries", description: "Evaluate new inquiries and propose a lead qualification update.", status: "Active", trigger: "Inbox message", updated: "12 min ago", runs: 28, owner: "Olivia Martin" },
  { id: 2, name: "Create opportunity follow-ups", description: "Create a task when an opportunity moves to Qualified.", status: "Paused", trigger: "Status changed", updated: "Yesterday", runs: 14, owner: "Sam Rivera" },
  { id: 3, name: "Weekly lead hygiene review", description: "Identify inactive leads and prepare archive recommendations.", status: "Active", trigger: "Schedule", updated: "Feb 20", runs: 9, owner: "Olivia Martin" },
  { id: 4, name: "Notify external project channel", description: "Prepare a notification when an onboarding task is created.", status: "Error", trigger: "Record created", updated: "Feb 19", runs: 3, owner: "Maya Chen", integrationError: true },
  { id: 5, name: "Finance record review", description: "Route restricted account changes to the Finance team.", status: "Draft", trigger: "Status changed", updated: "Feb 18", runs: 0, owner: "Finance team", restricted: true },
];

const toneFor = (status: WorkflowStatus): Tone =>
  status === "Active" ? "green" : status === "Paused" || status === "Draft" ? "amber" : "red";

export function WorkflowsWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [workflows, setWorkflows] = useState(initialWorkflows);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [trigger, setTrigger] = useState("All triggers");
  const [selectedId, setSelectedId] = useState(1);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<WorkflowDefinition | null>(null);
  const [name, setName] = useState("");
  const [editorTrigger, setEditorTrigger] = useState<Trigger>("Record created");
  const [schedule, setSchedule] = useState("Every weekday at 9:00 AM");
  const [runDetail, setRunDetail] = useState(false);
  const [loading, setLoading] = useState(false);
  const filtered = useMemo(() => workflows.filter((workflow) =>
    `${workflow.name} ${workflow.description} ${workflow.owner}`.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || workflow.status === status) &&
    (trigger === "All triggers" || workflow.trigger === trigger),
  ), [workflows, search, status, trigger]);
  const selected = workflows.find((workflow) => workflow.id === selectedId) || workflows[0];
  const openEditor = (workflow?: WorkflowDefinition) => {
    setEditing(workflow || null);
    setName(workflow?.name || "");
    setEditorTrigger(workflow?.trigger || "Record created");
    setSchedule("Every weekday at 9:00 AM");
    setEditorOpen(true);
  };
  const save = () => {
    if (editing) setWorkflows((current) => current.map((workflow) => workflow.id === editing.id ? { ...workflow, name, trigger: editorTrigger, updated: "Just now" } : workflow));
    else {
      const next: WorkflowDefinition = { id: Date.now(), name, description: "New workflow definition awaiting configuration.", status: "Draft", trigger: editorTrigger, updated: "Just now", runs: 0, owner: "Olivia Martin" };
      setWorkflows((current) => [next, ...current]);
      setSelectedId(next.id);
    }
    setEditorOpen(false);
    onToast(editing ? "Workflow updated" : "Workflow created as draft");
  };
  const toggleStatus = () => {
    if (selected.restricted || selected.integrationError) return;
    const next = selected.status === "Active" ? "Paused" : "Active";
    setWorkflows((current) => current.map((workflow) => workflow.id === selected.id ? { ...workflow, status: next, updated: "Just now" } : workflow));
    onToast(next === "Active" ? "Workflow activated" : "Workflow paused");
  };
  const duplicate = () => {
    const next = { ...selected, id: Date.now(), name: `${selected.name} copy`, status: "Draft" as WorkflowStatus, runs: 0, updated: "Just now", restricted: false };
    setWorkflows((current) => [next, ...current]);
    setSelectedId(next.id);
    onToast("Workflow duplicated as draft");
  };
  const testRun = () => {
    setLoading(true);
    window.setTimeout(() => { setLoading(false); setRunDetail(true); onToast("Sandbox run completed"); }, 700);
  };
  return (
    <main className="module-main operations-main workflows-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Governed automation</div><h1>Workflows</h1><p>Create and inspect controlled automations with explicit approval steps.</p></div><Button variant="primary" onClick={() => openEditor()}><Plus size={15} /> New workflow</Button></div>
      <div className="workflow-layout">
        <section className="panel workflow-library">
          <div className="operations-toolbar workflow-toolbar"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search workflows" aria-label="Search workflows" /></label><Button size="icon" aria-label="Reset workflow filters" onClick={() => { setStatus("All statuses"); setTrigger("All triggers"); }}><Filter size={14} /></Button></div>
          <div className="workflow-filters"><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter workflow status"><option>All statuses</option><option>Active</option><option>Paused</option><option>Draft</option><option>Error</option></select><select value={trigger} onChange={(event) => setTrigger(event.target.value)} aria-label="Filter workflow trigger"><option>All triggers</option><option>Record created</option><option>Status changed</option><option>Schedule</option><option>Inbox message</option></select></div>
          <div className="workflow-list">{filtered.length ? filtered.map((workflow) => <button className={selected.id === workflow.id ? "active" : ""} key={workflow.id} onClick={() => setSelectedId(workflow.id)}><span className="operation-icon"><Workflow size={15} /></span><span><strong>{workflow.name}</strong><small>{workflow.trigger} · {workflow.runs} runs</small></span><Badge tone={toneFor(workflow.status)}>{workflow.status}</Badge></button>) : <div className="module-empty compact"><Workflow size={24} /><strong>No workflows found</strong><p>Change the search or filters.</p></div>}</div>
        </section>
        <section className="panel workflow-detail">
          <header><div><div className="workflow-title"><h2>{selected.name}</h2><Badge tone={toneFor(selected.status)}>{selected.status}</Badge></div><p>{selected.description}</p></div><Button size="icon" variant="ghost" aria-label="Edit workflow" disabled={selected.restricted} onClick={() => openEditor(selected)}><MoreHorizontal size={16} /></Button></header>
          <div className="workflow-actions"><Button size="sm" onClick={() => openEditor(selected)} disabled={selected.restricted}><Edit3 size={13} /> Edit</Button><Button size="sm" onClick={duplicate}><Copy size={13} /> Duplicate</Button><Button size="sm" disabled={selected.restricted || selected.integrationError} onClick={toggleStatus}>{selected.status === "Active" ? <><Pause size={13} /> Pause</> : <><Play size={13} /> Activate</>}</Button><Button size="sm" variant="primary" disabled={selected.integrationError || selected.restricted || selected.status === "Draft" || loading} onClick={testRun}>{loading ? <LoaderCircleIcon /> : <Terminal size={13} />} Test in sandbox</Button></div>
          {selected.restricted && <div className="permission-state workflow-state"><BadgeCheck size={17} /><span><strong>Restricted workflow</strong><small>Only Finance administrators can edit or activate this definition.</small></span></div>}
          {selected.integrationError && <div className="state-banner error"><Link2Off size={16} /><span><strong>Integration unavailable</strong><small>The external project channel is not connected. Live delivery cannot be configured.</small></span><Button size="sm" disabled>Configure</Button></div>}
          <div className="workflow-canvas">
            <WorkflowNode icon={Zap} kind="Trigger" title={selected.trigger} detail={selected.trigger === "Schedule" ? "Every Monday at 9:00 AM" : "When matching workspace activity occurs"} />
            <span className="workflow-connector" />
            <WorkflowNode icon={GitBranch} kind="Condition" title="Record meets criteria" detail="Status is open and owner is assigned" />
            <span className="workflow-connector" />
            <WorkflowNode icon={Sparkles} kind="Action" title="Prepare proposed change" detail="Create a local action payload" />
            <span className="workflow-connector" />
            <WorkflowNode icon={BadgeCheck} kind="Approval" title="Reviewer decision" detail="Approval required before execution" approval />
          </div>
          <div className="workflow-bottom-grid">
            <section><div className="section-title"><h3>Schedule</h3><CalendarClock size={15} /></div>{selected.trigger === "Schedule" ? <div className="schedule-card"><strong>Every Monday at 9:00 AM</strong><span>Organization time zone</span></div> : <div className="module-empty compact"><Clock3 size={20} /><strong>Event-triggered</strong><p>No recurring schedule is configured.</p></div>}</section>
            <section><div className="section-title"><h3>Execution history</h3><button onClick={() => setRunDetail(true)}>View run</button></div><div className="mini-run"><span className="status-dot dot-green" /><div><strong>Sandbox test completed</strong><small>Yesterday · 18 sec</small></div><ChevronRight size={14} /></div><div className="mini-run"><span className={`status-dot ${selected.integrationError ? "dot-red" : "dot-green"}`} /><div><strong>{selected.integrationError ? "Configuration failed" : "Definition validated"}</strong><small>Feb 20</small></div><ChevronRight size={14} /></div></section>
          </div>
        </section>
      </div>

      <Modal open={editorOpen} title={editing ? "Edit workflow" : "New workflow"} description="Configure a local workflow definition. Activation is a separate action." onClose={() => setEditorOpen(false)}>
        <div className="dialog-body"><label className="field"><span>Workflow name</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Describe the workflow outcome" /></label><label className="field"><span>Trigger</span><select value={editorTrigger} onChange={(event) => setEditorTrigger(event.target.value as Trigger)}><option>Record created</option><option>Status changed</option><option>Schedule</option><option>Inbox message</option></select></label>{editorTrigger === "Schedule" && <label className="field"><span>Schedule</span><select value={schedule} onChange={(event) => setSchedule(event.target.value)}><option>Every weekday at 9:00 AM</option><option>Every Monday at 9:00 AM</option><option>First day of each month</option></select></label>}<div className="validation-summary"><CheckCircle2 size={16} /><span><strong>Approval step included</strong><small>All proposed actions require review before execution.</small></span></div>{name && name.length < 4 && <div className="state-banner error"><CircleAlert size={15} /><span><strong>Configuration error</strong><small>Use at least four characters for the workflow name.</small></span></div>}</div>
        <div className="dialog-footer"><Button onClick={() => setEditorOpen(false)}>Cancel</Button><Button variant="primary" disabled={name.trim().length < 4} onClick={save}><Save size={14} /> Save workflow</Button></div>
      </Modal>

      {runDetail && <><button className="drawer-backdrop" aria-label="Close workflow run" onClick={() => setRunDetail(false)} /><aside className="drawer operations-drawer"><div className="drawer-header"><div><h2>Workflow run details</h2><p>{selected.name} · Sandbox</p></div><Button size="icon" variant="ghost" aria-label="Close workflow run" onClick={() => setRunDetail(false)}><X size={17} /></Button></div><div className="drawer-content"><div className="sandbox-callout"><Terminal size={16} /><span><strong>Sandbox execution</strong><small>No live delivery or external changes occurred.</small></span></div><section className="run-section"><h3>Execution steps</h3><div className="run-timeline"><div className="run-step complete"><span><Zap size={14} /></span><div><strong>Trigger evaluated</strong><small>{selected.trigger}</small></div><Check size={14} /></div><div className="run-step complete"><span><GitBranch size={14} /></span><div><strong>Condition matched</strong><small>Record met configured criteria</small></div><Check size={14} /></div><div className="run-step complete"><span><BadgeCheck size={14} /></span><div><strong>Approval simulated</strong><small>Sandbox reviewer checkpoint</small></div><Check size={14} /></div></div></section><div className="execution-result"><CheckCircle2 size={17} /><span><strong>Sandbox run completed</strong><small>Validation passed. This does not indicate live delivery readiness.</small></span></div></div></aside></>}
    </main>
  );
}

function WorkflowNode({ icon: Icon, kind, title, detail, approval }: { icon: typeof Zap; kind: string; title: string; detail: string; approval?: boolean }) {
  return <div className={`workflow-node ${approval ? "approval" : ""}`}><span><Icon size={16} /></span><div><small>{kind}</small><strong>{title}</strong><p>{detail}</p></div><ChevronRight size={14} /></div>;
}

function LoaderCircleIcon() {
  return <span className="inline-loader" />;
}
