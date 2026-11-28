import { useEffect, useMemo, useState } from "react";
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
import { createWorkflowRow, failureMessage, listLeadChoices, listWorkflowRunRows, listWorkflows, relativeTime, reviewWorkflowRun, startWorkflow, updateWorkflowRow, workflowCommand, type WorkflowRunDetail } from "@/data/resources";
import { Badge, Button, Modal, type Tone } from "./components";

type WorkflowStatus = "Active" | "Paused" | "Draft" | "Error";
type Trigger = "Record created" | "Status changed" | "Schedule" | "Manual";
type WorkflowDefinition = {
  id: string;
  name: string;
  slug: string;
  version: number;
  description: string;
  status: WorkflowStatus;
  trigger: Trigger;
  updated: string;
  runs: number;
  owner: string;
  actions: { type: string; title?: string; note?: string }[];
  conditions: { value: string }[];
  otherwise: { type: string; title?: string; note?: string }[];
  interval?: number;
  integrationError?: boolean;
  restricted?: boolean;
};

const triggerLabel = (value: string): Trigger => value === "schedule" ? "Schedule" : value.includes("status") || value.includes("stage") ? "Status changed" : value === "lead_created" ? "Record created" : "Manual";
const intervalSeconds = (label: string) => label === "Every week" ? 604800 : label === "Every 30 days" ? 2592000 : 86400;
const intervalLabel = (seconds?: number) => seconds === 604800 ? "Every week" : seconds === 2592000 ? "Every 30 days" : seconds ? "Every day" : "No interval stored";

const toneFor = (status: WorkflowStatus): Tone =>
  status === "Active" ? "green" : status === "Paused" || status === "Draft" ? "amber" : "red";

export function WorkflowsWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [runs, setRuns] = useState<WorkflowRunDetail[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [trigger, setTrigger] = useState("All triggers");
  const [selectedId, setSelectedId] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<WorkflowDefinition | null>(null);
  const [name, setName] = useState("");
  const [editorTrigger, setEditorTrigger] = useState<Trigger>("Record created");
  const [schedule, setSchedule] = useState("Every day");
  const [condition, setCondition] = useState("qualified");
  const [otherwiseTitle, setOtherwiseTitle] = useState("");
  const [runOpen, setRunOpen] = useState(false);
  const [leads, setLeads] = useState<{ id: string; title: string; status: string }[]>([]);
  const [runLead, setRunLead] = useState("");
  const [runDetail, setRunDetail] = useState(false);
  const [loading, setLoading] = useState(false);
  const filtered = useMemo(() => workflows.filter((workflow) =>
    `${workflow.name} ${workflow.description} ${workflow.owner}`.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || workflow.status === status) &&
    (trigger === "All triggers" || workflow.trigger === trigger),
  ), [workflows, search, status, trigger]);
  const selected = workflows.find((workflow) => workflow.id === selectedId) || workflows[0] || { id: "", name: "No workflows", slug: "", version: 1, description: "This workspace has no workflow definitions.", status: "Draft" as WorkflowStatus, trigger: "Record created" as Trigger, updated: "", runs: 0, owner: "", actions: [], conditions: [], otherwise: [] };
  const mapWorkflow = (row: { id: string; name: string; slug: string; version: number; description: string | null; active: boolean; definition: { trigger: string; actions?: { type: string; title?: string; note?: string }[]; otherwise_actions?: { type: string; title?: string; note?: string }[]; conditions?: { value: string }[]; interval_seconds?: number }; updated_at: string; last_run_at: string | null }): WorkflowDefinition => ({
    id: row.id,
    name: row.name,
    slug: row.slug,
    version: row.version,
    description: row.description || "Workflow definition",
    status: row.active ? "Active" : "Paused",
    trigger: triggerLabel(row.definition?.trigger || "manual"),
    updated: row.updated_at.slice(0, 10),
    runs: 0,
    owner: row.last_run_at ? `Last run ${relativeTime(row.last_run_at)}` : "No runs recorded",
    actions: row.definition?.actions || [],
    conditions: row.definition?.conditions || [],
    otherwise: row.definition?.otherwise_actions || [],
    interval: row.definition?.interval_seconds,
  });
  const reload = () => listWorkflows().then((rows) => {
    const next = rows.filter((row) => !row.archived_at).map(mapWorkflow);
    setWorkflows(next);
    setSelectedId((current) => next.some((workflow) => workflow.id === current) ? current : next[0]?.id || "");
    return next;
  });
  useEffect(() => {
    reload().catch((error: unknown) => onToast(failureMessage(error)));
  }, [onToast]);
  useEffect(() => {
    if (!selectedId) return;
    listWorkflowRunRows(selectedId).then(setRuns).catch(() => setRuns([]));
  }, [selectedId]);
  const openEditor = (workflow?: WorkflowDefinition) => {
    setEditing(workflow || null);
    setName(workflow?.name || "");
    setEditorTrigger(workflow?.trigger || "Record created");
    setSchedule(intervalLabel(workflow?.interval) === "No interval stored" ? "Every day" : intervalLabel(workflow?.interval));
    setCondition(workflow?.conditions[0]?.value || "qualified");
    setOtherwiseTitle(workflow?.otherwise.find((action) => action.type === "create_task")?.title || "");
    setEditorOpen(true);
  };
  const save = () => {
    const interval = intervalSeconds(schedule);
    const branch = { condition, otherwiseTitle };
    const request = editing ? updateWorkflowRow(editing, name, editorTrigger, interval, branch) : createWorkflowRow(name, editorTrigger, interval, branch);
    void request.then((saved) => {
      const next = mapWorkflow(saved);
      setWorkflows((current) => editing ? current.map((workflow) => workflow.id === saved.id ? next : workflow) : [next, ...current]);
      setSelectedId(saved.id);
      setEditorOpen(false);
      onToast(editing ? "Workflow updated" : "Workflow created as a paused definition");
    }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const toggleStatus = () => {
    if (!selected.id) return;
    const action = selected.status === "Active" ? "pause" : "activate";
    void workflowCommand(selected.id, action).then(() => {
      const next = action === "activate" ? "Active" : "Paused";
      setWorkflows((current) => current.map((workflow) => workflow.id === selected.id ? { ...workflow, status: next } : workflow));
      onToast(next === "Active" ? "Workflow activated" : "Workflow paused");
    }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const duplicate = () => {
    if (!selected.id) return;
    void workflowCommand(selected.id, "duplicate").then(() => { onToast("Workflow duplicated"); return reload(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const needsLead = selected.trigger === "Record created" || selected.trigger === "Status changed";
  const executeRun = (dryRun: boolean) => {
    if (!selected.id || (needsLead && !runLead)) return;
    setLoading(true);
    void startWorkflow(selected.id, dryRun, needsLead ? { leadId: runLead } : undefined).then(() => {
      setRunOpen(false);
      setRunDetail(true);
      onToast(dryRun ? "Dry run recorded. No records were changed." : "Local run recorded.");
      return refreshRunsUntilSettled(selected.id);
    }).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setLoading(false));
  };
  const testRun = () => {
    if (!selected.id) return;
    if (!needsLead) {
      setLoading(true);
      void startWorkflow(selected.id, true).then(() => { setRunDetail(true); onToast("Dry run recorded. No records were changed."); return refreshRunsUntilSettled(selected.id); }).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setLoading(false));
      return;
    }
    const matchingStatus = selected.conditions[0]?.value;
    listLeadChoices(matchingStatus).then((rows) => {
      setLeads(rows);
      setRunLead(rows.find((lead) => lead.status === matchingStatus)?.id || rows[0]?.id || "");
      setRunOpen(true);
    }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const review = (runId: string, decision: "approve" | "reject") => {
    void reviewWorkflowRun(selected.id, runId, decision).then(() => { onToast(decision === "approve" ? "Internal step approved" : "Workflow run rejected"); return listWorkflowRunRows(selected.id).then(setRuns); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const openRunDetails = () => {
    if (!selected.id) return;
    void listWorkflowRunRows(selected.id).then((next) => { setRuns(next); setRunDetail(true); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const refreshRunsUntilSettled = async (workflowId: string): Promise<void> => {
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline) {
      const next = await listWorkflowRunRows(workflowId);
      setRuns(next);
      if (next[0] && !["pending", "dispatching"].includes(next[0].status)) return;
      await new Promise((resolve) => window.setTimeout(resolve, 250));
    }
  };
  return (
    <main className="module-main operations-main workflows-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Governed automation</div><h1>Workflows</h1><p>Create and inspect controlled automations with explicit approval steps.</p></div><Button variant="primary" onClick={() => openEditor()}><Plus size={15} /> New workflow</Button></div>
      <div className="workflow-layout">
        <section className="panel workflow-library">
          <div className="operations-toolbar workflow-toolbar"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search workflows" aria-label="Search workflows" /></label><Button size="icon" aria-label="Reset workflow filters" onClick={() => { setStatus("All statuses"); setTrigger("All triggers"); }}><Filter size={14} /></Button></div>
          <div className="workflow-filters"><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter workflow status"><option>All statuses</option><option>Active</option><option>Paused</option><option>Draft</option><option>Error</option></select><select value={trigger} onChange={(event) => setTrigger(event.target.value)} aria-label="Filter workflow trigger"><option>All triggers</option><option>Record created</option><option>Status changed</option><option>Schedule</option><option>Manual</option></select></div>
          <div className="workflow-list">{filtered.length ? filtered.map((workflow) => <button className={selected.id === workflow.id ? "active" : ""} key={workflow.id} onClick={() => setSelectedId(workflow.id)}><span className="operation-icon"><Workflow size={15} /></span><span><strong>{workflow.name}</strong><small>{workflow.trigger} · {workflow.owner}</small></span><Badge tone={toneFor(workflow.status)}>{workflow.status}</Badge></button>) : <div className="module-empty compact"><Workflow size={24} /><strong>No workflows found</strong><p>Change the search or filters.</p></div>}</div>
        </section>
        <section className="panel workflow-detail">
          <header><div><div className="workflow-title"><h2>{selected.name}</h2><Badge tone={toneFor(selected.status)}>{selected.status}</Badge></div><p>{selected.description}</p></div><Button size="icon" variant="ghost" aria-label="Edit workflow" disabled={selected.restricted} onClick={() => openEditor(selected)}><MoreHorizontal size={16} /></Button></header>
          <div className="workflow-actions"><Button size="sm" onClick={() => openEditor(selected)} disabled={selected.restricted}><Edit3 size={13} /> Edit</Button><Button size="sm" onClick={duplicate}><Copy size={13} /> Duplicate</Button><Button size="sm" disabled={selected.restricted || selected.integrationError} onClick={toggleStatus}>{selected.status === "Active" ? <><Pause size={13} /> Pause</> : <><Play size={13} /> Activate</>}</Button><Button size="sm" variant="primary" disabled={selected.integrationError || selected.restricted || selected.status === "Draft" || loading} onClick={testRun}>{loading ? <LoaderCircleIcon /> : <Terminal size={13} />} Test in sandbox</Button></div>
          {selected.restricted && <div className="permission-state workflow-state"><BadgeCheck size={17} /><span><strong>Restricted workflow</strong><small>Only Finance administrators can edit or activate this definition.</small></span></div>}
          {selected.integrationError && <div className="state-banner error"><Link2Off size={16} /><span><strong>Integration unavailable</strong><small>The external project channel is not connected. Live delivery cannot be configured.</small></span><Button size="sm" disabled>Configure</Button></div>}
          <div className="workflow-canvas">
            <WorkflowNode icon={Zap} kind="Trigger" title={selected.trigger} detail={selected.trigger === "Schedule" ? intervalLabel(selected.interval) : "Stored trigger"} />
            {selected.conditions.map((entry) => <span className="workflow-step" key={entry.value}><span className="workflow-connector" /><WorkflowNode icon={GitBranch} kind="Condition" title={`Lead status equals ${entry.value}`} detail="Matching records follow this path" /></span>)}
            {selected.actions.length ? selected.actions.map((action) => <span className="workflow-step" key={`match-${action.type}-${action.title || action.note || ""}`}><span className="workflow-connector" /><WorkflowNode icon={action.type === "require_approval" ? BadgeCheck : Sparkles} kind={action.type === "require_approval" ? "Approval" : "Matched action"} title={action.title || action.note || action.type.replaceAll("_", " ")} detail="Stored workflow step" approval={action.type === "require_approval"} /></span>) : null}
            {selected.otherwise.map((action) => <span className="workflow-step" key={`else-${action.type}-${action.title || action.note || ""}`}><span className="workflow-connector" /><WorkflowNode icon={GitBranch} kind="Otherwise" title={action.title || action.note || action.type.replaceAll("_", " ")} detail="Used when the condition does not match" /></span>)}
          </div>
          <div className="workflow-bottom-grid">
            <section><div className="section-title"><h3>Schedule</h3><CalendarClock size={15} /></div>{selected.trigger === "Schedule" ? <div className="schedule-card"><strong>{intervalLabel(selected.interval)}</strong><span>Stored repeat interval</span></div> : <div className="module-empty compact"><Clock3 size={20} /><strong>Event-triggered</strong><p>No recurring schedule is stored.</p></div>}</section>
            <section><div className="section-title"><h3>Execution history</h3><button onClick={openRunDetails}>View run</button></div>{runs.length ? runs.slice(0, 4).map((run) => <div className="mini-run" key={run.id}><span className={`status-dot ${run.error ? "dot-red" : "dot-green"}`} /><div><strong>{run.status}{run.dry_run ? " · dry run" : ""}</strong><small>{run.created_at.slice(0, 16).replace("T", " ")}</small></div><ChevronRight size={14} /></div>) : <div className="module-empty compact"><Clock3 size={20} /><strong>No runs yet</strong><p>A dry run records a preview and does not change customer records.</p></div>}</section>
          </div>
        </section>
      </div>

      <Modal open={editorOpen} title={editing ? "Edit workflow" : "New workflow"} description="Configure a local workflow definition. Activation is a separate action." onClose={() => setEditorOpen(false)}>
        <div className="dialog-body"><label className="field"><span>Workflow name</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Describe the workflow outcome" /></label><label className="field"><span>Trigger</span><select value={editorTrigger} onChange={(event) => setEditorTrigger(event.target.value as Trigger)}><option>Record created</option><option>Status changed</option><option>Schedule</option><option>Manual</option></select></label>{editorTrigger === "Schedule" && <label className="field"><span>Schedule</span><select value={schedule} onChange={(event) => setSchedule(event.target.value)}><option>Every day</option><option>Every week</option><option>Every 30 days</option></select></label>}{editorTrigger === "Status changed" && <><label className="field"><span>Matching lead status</span><select aria-label="Workflow condition" value={condition} onChange={(event) => setCondition(event.target.value)}><option value="new">New</option><option value="contacted">Contacted</option><option value="qualified">Qualified</option><option value="unqualified">Unqualified</option><option value="won">Won</option><option value="lost">Lost</option></select></label><label className="field"><span>Otherwise task</span><input aria-label="Otherwise task" value={otherwiseTitle} onChange={(event) => setOtherwiseTitle(event.target.value)} placeholder="Optional task when the status does not match" /></label></>}<div className="validation-summary"><CheckCircle2 size={16} /><span><strong>Approval step included</strong><small>Each path requires review before its follow-up task.</small></span></div>{editing?.status === "Active" && <div className="state-banner error"><CircleAlert size={15} /><span><strong>Pause before editing</strong><small>An active workflow must be paused before its definition can change.</small></span></div>}{name && name.length < 4 && <div className="state-banner error"><CircleAlert size={15} /><span><strong>Configuration error</strong><small>Use at least four characters for the workflow name.</small></span></div>}</div>
        <div className="dialog-footer"><Button onClick={() => setEditorOpen(false)}>Cancel</Button><Button variant="primary" disabled={name.trim().length < 4 || editing?.status === "Active"} onClick={save}><Save size={14} /> Save workflow</Button></div>
      </Modal>

      <Modal open={runOpen} title="Run workflow" description="Choose the lead this trigger requires. A preview does not change records." onClose={() => setRunOpen(false)}>
        <div className="dialog-body"><label className="field"><span>Lead</span><select aria-label="Workflow lead" value={runLead} onChange={(event) => setRunLead(event.target.value)}>{leads.map((lead) => <option key={lead.id} value={lead.id}>{lead.title}</option>)}</select></label></div>
        <div className="dialog-footer"><Button onClick={() => executeRun(true)} disabled={!runLead || loading}>Preview</Button><Button variant="primary" onClick={() => executeRun(false)} disabled={!runLead || loading}>Run locally</Button></div>
      </Modal>

      {runDetail && <><button className="drawer-backdrop" aria-label="Close workflow run" onClick={() => setRunDetail(false)} /><aside className="drawer operations-drawer"><div className="drawer-header"><div><h2>Workflow run details</h2><p>{selected.name}</p></div><Button size="icon" variant="ghost" aria-label="Close workflow run" onClick={() => setRunDetail(false)}><X size={17} /></Button></div><div className="drawer-content">{runs.length ? runs.map((run) => <section className="run-section" key={run.id}><h3>{run.status}{run.dry_run ? " · dry run" : ""}{run.branch ? ` · ${run.branch}` : ""}</h3><p className="detail-copy">{run.created_at.slice(0, 16).replace("T", " ")}{run.error ? ` · ${run.error}` : ""}</p>{run.steps?.length ? <div className="run-timeline">{run.steps.map((step, index) => <div className={`run-step ${step.status === "failed" ? "failed" : "complete"}`} key={`${step.type}-${index}`}><span><Zap size={14} /></span><div><strong>{step.type}</strong><small>{step.status}</small></div>{step.status === "failed" ? <AlertTriangle size={14} /> : <Check size={14} />}</div>)}</div> : null}{run.status === "awaiting_approval" && !run.dry_run ? <div className="plan-actions"><Button size="sm" onClick={() => review(run.id, "reject")}>Reject</Button><Button size="sm" variant="primary" onClick={() => review(run.id, "approve")}>Approve internal step</Button></div> : null}</section>) : <div className="module-empty"><Clock3 size={22} /><strong>No runs recorded</strong><p>A dry run records a preview and does not change customer records.</p></div>}</div></aside></>}
    </main>
  );
}

function WorkflowNode({ icon: Icon, kind, title, detail, approval }: { icon: typeof Zap; kind: string; title: string; detail: string; approval?: boolean }) {
  return <div className={`workflow-node ${approval ? "approval" : ""}`}><span><Icon size={16} /></span><div><small>{kind}</small><strong>{title}</strong><p>{detail}</p></div><ChevronRight size={14} /></div>;
}

function LoaderCircleIcon() {
  return <span className="inline-loader" />;
}
