"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Cable, Check, ChevronRight, Clock3, GitBranch, ListChecks, Plus, Search, ShieldCheck, Workflow, Zap } from "lucide-react";
import { useRef, useState } from "react";

import { ConfirmButton } from "@/components/confirm-button";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { listPipelineStages } from "@/lib/opportunities";
import { cn } from "@/lib/utils";
import { createWorkflowDefinition, deleteWorkflowDefinition, updateWorkflowDefinition, validateWorkflow, workflowAction, type WorkflowAction, type WorkflowCondition, type WorkflowDefinition, type WorkflowGraph, type WorkflowTrigger } from "@/lib/workflow-definitions";
import { listWorkflowDefinitions } from "@/lib/workflow-definitions";
import { WorkflowRunPanel } from "./workflow-run-panel";

export const triggerLabels: Record<WorkflowTrigger, string> = {
  manual: "Manual start",
  lead_created: "Lead created",
  lead_status_changed: "Lead status changed",
  opportunity_stage_changed: "Opportunity stage changed",
  schedule: "Recurring schedule",
};
export const stepLabels: Record<string, string> = {
  create_task: "Create task", update_lead: "Update lead status", require_approval: "Require approval",
  prepare_follow_up: "Draft follow-up for approval", condition: "Condition", load_context: "Load CRM record",
  branch: "Execution path", external_dispatch: "External dispatch",
};
const leadStatuses = ["new", "contacted", "qualified", "unqualified", "won", "lost"];
const controlClass = "h-9 w-full min-w-0 rounded-md border border-input bg-card px-2 text-sm";
type ActionPath = "actions" | "otherwise_actions";
type NodeSelection = { kind: "trigger" } | { kind: "condition"; index: number } | { kind: "action"; index: number; path: ActionPath };
type Saved = (workflow: WorkflowDefinition) => void;

function lifecycle(item: WorkflowDefinition) {
  return item.archived_at ? "Archived" : item.active ? "Active" : item.activated_at ? "Paused" : "Draft";
}

export function WorkflowStudio({ organizationId, requestedWorkflow, requestedRun, showArchived }: {
  organizationId: string; requestedWorkflow?: string; requestedRun?: string; showArchived?: boolean;
}) {
  const client = useQueryClient();
  const queryKey = ["workflow-definitions", organizationId];
  const workflows = useQuery({ queryKey, queryFn: () => listWorkflowDefinitions(organizationId) });
  const [selectedId, setSelectedId] = useState(requestedWorkflow);
  const [search, setSearch] = useState("");
  const [archived, setArchived] = useState(Boolean(showArchived));
  const [createOpen, setCreateOpen] = useState(false);
  const items = workflows.data?.filter((item) => Boolean(item.archived_at) === archived &&
    item.name.toLowerCase().includes(search.trim().toLowerCase())) ?? [];
  const selected = items.find((item) => item.id === selectedId) ?? items[0];
  const saved: Saved = (item) => {
    client.setQueryData<WorkflowDefinition[]>(queryKey, (current) => [item, ...(current ?? []).filter(({ id }) => id !== item.id)]);
    setSelectedId(item.id);
    void client.invalidateQueries({ queryKey });
  };
  return (
    <section aria-label="Workflow builder" className="space-y-5">
      <PageHeader title="Workflows" eyebrow="Automation" actions={
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild><Button><Plus className="size-4" />New workflow</Button></DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>New workflow</DialogTitle><DialogDescription>Choose a starting event and an initial action. You can add more steps on the canvas.</DialogDescription></DialogHeader>
            <NewWorkflow organizationId={organizationId} onSaved={(item) => {
              setSearch(""); setArchived(false); saved(item); setCreateOpen(false);
            }} />
          </DialogContent>
        </Dialog>
      }>Build repeatable processes for leads, opportunities, and team tasks.</PageHeader>
      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <aside className="min-w-0 rounded-xl border border-border bg-card p-3" aria-label="Workflow library">
          <div className="flex items-center justify-between gap-2 px-1"><h2 className="text-sm font-semibold">Workflow library</h2><Badge variant="secondary">{items.length}</Badge></div>
          <div className="relative mt-3"><Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" aria-hidden="true" />
            <Input className="pl-8" aria-label="Search workflows" placeholder="Search workflows" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div className="my-3 flex gap-1">
            <Button size="sm" variant={archived ? "ghost" : "secondary"} aria-pressed={!archived} onClick={() => setArchived(false)}>Current</Button>
            <Button size="sm" variant={archived ? "secondary" : "ghost"} aria-pressed={archived} onClick={() => setArchived(true)}>Archived</Button>
          </div>
          {workflows.isPending ? <Skeleton className="h-24" /> : null}
          {workflows.error ? <RequestError error={workflows.error} /> : null}
          <ul className="max-h-[32rem] space-y-1 overflow-y-auto">
            {items.map((item) => <li key={item.id}>
              <button type="button" aria-pressed={item.id === selected?.id} onClick={() => setSelectedId(item.id)}
                className="flex w-full min-w-0 items-center gap-2 rounded-lg border border-transparent px-2 py-2.5 text-left hover:bg-muted aria-pressed:border-primary/25 aria-pressed:bg-accent">
                <span className="grid size-8 shrink-0 place-items-center rounded-md bg-primary/10 text-primary"><Workflow className="size-4" /></span>
                <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{item.name}</span><span className="text-xs text-muted-foreground">{lifecycle(item)}</span></span>
                <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
              </button>
            </li>)}
          </ul>
          {!workflows.isPending && !workflows.error && !items.length ? <p className="px-1 py-2 text-xs text-muted-foreground">{search ? "No workflows match your search." : archived ? "No archived workflows." : "Your first workflow will appear here."}</p> : null}
        </aside>
        {selected ? <WorkflowEditor key={`${selected.id}:${selected.version}:${selected.active}`} item={selected} organizationId={organizationId} requestedRun={selected.id === requestedWorkflow ? requestedRun : undefined} saved={(item) => {
          if (!item.archived_at) { setArchived(false); setSearch(""); }
          saved(item);
        }} onArchived={() => void client.invalidateQueries({ queryKey })} /> : (
          <div className="grid min-h-80 place-items-center rounded-xl border border-dashed border-border bg-card p-6 text-center">
            <div className="max-w-sm"><Cable className="mx-auto mb-3 size-8 text-primary" aria-hidden="true" /><h2 className="font-semibold">No workflow selected</h2><p className="mt-1 text-sm text-muted-foreground">Open a workflow from the library or create a new one to get started.</p></div>
          </div>
        )}
      </div>
    </section>
  );
}

function NewWorkflow({ organizationId, onSaved }: { organizationId: string; onSaved: Saved }) {
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState<WorkflowTrigger>("lead_created");
  const [title, setTitle] = useState("");
  const save = useMutation({
    mutationFn: () => createWorkflowDefinition(organizationId, {
      name: name.trim(), slug: `workflow-${crypto.randomUUID()}`,
      definition: { trigger, interval_seconds: 3600, actions: [{ type: "create_task", title: title.trim() }] },
    }),
    onSuccess: onSaved,
  });
  return (
    <form className="mt-4 grid gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <label className="grid gap-1 text-sm">Workflow name<Input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="grid gap-1 text-sm">Trigger<TriggerSelect trigger={trigger} onChange={setTrigger} /></label>
      <label className="grid gap-1 text-sm">Task title<Input required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      {save.error ? <RequestError error={save.error} /> : null}
      <Button type="submit" disabled={save.isPending || !name.trim() || !title.trim()}>{save.isPending ? "Creating…" : "Create draft"}</Button>
    </form>
  );
}

function TriggerSelect({ trigger, onChange }: { trigger: WorkflowTrigger; onChange: (trigger: WorkflowTrigger) => void }) {
  return <select className={controlClass} value={trigger} onChange={(e) => onChange(e.target.value as WorkflowTrigger)}>
    {Object.entries(triggerLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
  </select>;
}

function WorkflowEditor({ item, organizationId, saved, onArchived, requestedRun }: {
  item: WorkflowDefinition; organizationId: string; saved: Saved; onArchived: () => void; requestedRun?: string;
}) {
  const [name, setName] = useState(item.name);
  const [description, setDescription] = useState(item.description ?? "");
  const [graph, setGraph] = useState(item.definition);
  const [selection, setSelection] = useState<NodeSelection>({ kind: "trigger" });
  const [view, setView] = useState<"builder" | "runs">(requestedRun ? "runs" : "builder");
  const nodePanel = useRef<HTMLDivElement>(null);
  const [notice, setNotice] = useState("");
  const readOnly = item.active || Boolean(item.archived_at);
  const dirty = JSON.stringify(graph) !== JSON.stringify(item.definition) || name !== item.name || description !== (item.description ?? "");
  const body = { name: name.trim(), slug: item.slug, description: description.trim() || null, definition: graph, expected_version: item.version };
  const save = useMutation({ mutationFn: () => updateWorkflowDefinition(organizationId, item.id, body), onSuccess: saved });
  const validate = useMutation({ mutationFn: () => validateWorkflow(organizationId, body), onSuccess: () => setNotice("Workflow validated.") });
  const transition = useMutation({
    mutationFn: (action: "activate" | "pause" | "duplicate") => workflowAction(organizationId, item.id, action),
    onSuccess: saved,
  });
  const archive = useMutation({ mutationFn: () => deleteWorkflowDefinition(organizationId, item.id), onSuccess: onArchived });
  const busy = save.isPending || validate.isPending || transition.isPending || archive.isPending;
  const error = save.error ?? transition.error ?? validate.error ?? archive.error;
  function changeGraph(next: WorkflowGraph) {
    setNotice(""); validate.reset(); setGraph(next);
  }
  return (
    <section aria-label="Workflow details" className="min-w-0 overflow-hidden rounded-xl border border-border bg-card">
      <header className="grid gap-4 border-b border-border p-4 md:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><h2 className="break-words font-semibold">{item.name}</h2><Badge variant={item.active ? "default" : "secondary"}>{lifecycle(item)}</Badge></div>
            {item.description ? <p className="mt-1 text-xs text-muted-foreground">{item.description}</p> : null}
            {item.next_run_at ? <p className="mt-1 text-xs text-muted-foreground">Next run {new Date(item.next_run_at).toLocaleString()}</p> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" disabled={busy || dirty} onClick={() => transition.mutate("duplicate")}>Duplicate</Button>
            {!item.archived_at ? <Button size="sm" variant={item.active ? "outline" : "default"} disabled={busy || dirty} onClick={() => transition.mutate(item.active ? "pause" : "activate")}>{item.active ? "Pause" : "Activate"}</Button> : null}
            {!readOnly ? <Button size="sm" variant="outline" disabled={busy || !dirty || !name.trim()} onClick={() => save.mutate()}>Save changes</Button> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant={view === "builder" ? "secondary" : "ghost"} aria-pressed={view === "builder"} onClick={() => setView("builder")}><Workflow className="size-4" />Canvas</Button>
          <Button size="sm" variant={view === "runs" ? "secondary" : "ghost"} aria-pressed={view === "runs"} onClick={() => setView("runs")}><Clock3 className="size-4" />Runs and approvals</Button>
          {view === "builder" ? <Button size="sm" variant="ghost" disabled={busy || !name.trim()} onClick={() => validate.mutate()}><Check className="size-4" />Validate</Button> : null}
        </div>
        {!item.archived_at && !item.active ? <p className="text-xs text-muted-foreground">Activation checks the trigger, conditions, and actions before this workflow can run. Pause it before editing.</p> : null}
        {notice ? <p role="status" className="text-sm text-success">{notice}</p> : null}
        {dirty ? <p className="text-xs text-warning">Unsaved changes</p> : null}
        {error ? <RequestError error={error} /> : null}
      </header>
      {view === "builder" ? (
        <div className="grid min-w-0 xl:grid-cols-[minmax(0,1fr)_18rem]">
          <WorkflowCanvas graph={graph} selection={selection} select={(node) => {
            setSelection(node);
            if (!window.matchMedia("(min-width: 1280px)").matches) {
              nodePanel.current?.focus({ preventScroll: true });
              nodePanel.current?.scrollIntoView({ block: "start" });
            }
          }} />
          <div ref={nodePanel} tabIndex={-1} className="min-w-0 scroll-mt-20 border-t border-border p-4 xl:border-t-0 xl:border-l">
            <NodeSettings organizationId={organizationId} graph={graph} update={changeGraph} selection={selection} select={setSelection} readOnly={readOnly || busy} />
            <details className="mt-5 border-t border-border pt-4">
              <summary className="cursor-pointer text-sm font-medium">Workflow settings</summary>
              <fieldset className="mt-3 grid gap-3" disabled={readOnly || busy}>
                <label className="grid gap-1 text-sm">Name<Input maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></label>
                <label className="grid gap-1 text-sm">Description<Textarea maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
              </fieldset>
              {!item.archived_at ? <div className="mt-3"><ConfirmButton size="sm" label="Archive workflow" confirmLabel="Confirm archive" pendingLabel="Archiving…" pending={archive.isPending} onConfirm={() => { if (!busy) archive.mutate(); }} /></div> : null}
            </details>
          </div>
        </div>
      ) : <WorkflowRunPanel organizationId={organizationId} workflow={item} dirty={dirty} labels={stepLabels} requestedRun={requestedRun} />}
    </section>
  );
}

type CanvasNode = { node: NodeSelection; label: string; detail: string; icon: typeof Zap };

function WorkflowCanvas({ graph, selection, select }: { graph: WorkflowGraph; selection: NodeSelection; select: (node: NodeSelection) => void }) {
  const conditions = graph.conditions ?? [];
  const triggerNodes: CanvasNode[] = [
    { node: { kind: "trigger" }, label: triggerLabels[graph.trigger], detail: "Trigger", icon: Zap },
    ...conditions.map((entry, index) => ({
      node: { kind: "condition" as const, index },
      label: `${entry.operator === "equals" ? "Is" : "Is not"} ${entry.value.replaceAll("-", " ")}`,
      detail: "Condition", icon: GitBranch,
    })),
  ];
  const actionNodes = (path: ActionPath): CanvasNode[] => (graph[path] ?? []).map((action, index) => ({
    node: { kind: "action", index, path }, label: stepLabels[action.type],
    detail: action.title || action.status || (action.type === "require_approval" ? "Human review" : "Action"),
    icon: action.type === "require_approval" ? ShieldCheck : ListChecks,
  }));
  function column(nodes: CanvasNode[]) {
    return <ol className="mx-auto w-full max-w-[21rem]">
      {nodes.map(({ node, label, detail, icon: Icon }, index) => {
        const active = node.kind === selection.kind &&
          (node.kind === "trigger" || ("index" in selection && selection.index === node.index)) &&
          (node.kind !== "action" || (selection.kind === "action" && selection.path === node.path));
        return <li key={node.kind === "trigger" ? "trigger" : `${node.kind}-${node.index}`}>
          {index > 0 ? <CanvasConnector /> : null}
          <button type="button" aria-pressed={active} onClick={() => select(node)} className={cn(
            "flex w-full min-w-0 items-center gap-3 rounded-xl border bg-card p-3 text-left shadow-sm hover:border-primary/60",
            active ? "border-primary ring-2 ring-primary/20" : "border-border",
          )}>
            <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg", node.kind === "trigger" ? "bg-primary/10 text-primary" : node.kind === "condition" ? "bg-warning/10 text-warning" : "bg-accent text-accent-foreground")}><Icon className="size-4" aria-hidden="true" /></span>
            <span className="min-w-0"><span className="block break-words text-xs text-muted-foreground">{detail}</span><span className="block break-words text-sm font-semibold">{label}</span></span>
          </button>
        </li>;
      })}
    </ol>;
  }
  return (
    <div className="min-w-0 bg-background p-4 [background-image:radial-gradient(var(--border-strong)_1px,transparent_1px)] [background-size:18px_18px] sm:p-6" aria-label="Workflow canvas">
      {conditions.length ? <>
        {column(triggerNodes)}
        <div aria-hidden="true" className="relative mx-auto hidden h-8 max-w-[44rem] text-primary/60 sm:block">
          <div className="absolute left-1/2 top-0 h-4 border-l border-current" />
          <div className="absolute inset-x-1/4 top-4 h-4 rounded-t border-x border-t border-current" />
        </div>
        <p className="mb-3 text-center text-xs text-muted-foreground sm:hidden">Matching records use the first path. Other records use the second.</p>
        <div className="mx-auto grid max-w-[44rem] grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-0">
          {(["actions", "otherwise_actions"] as const).map((path) => <section key={path} aria-label={path === "actions" ? "Conditions match" : "Otherwise"} className="min-w-0 px-1.5">
            <div className="mb-2 rounded-md border border-border bg-card px-2 py-1.5 text-center text-xs font-medium">{path === "actions" ? "Conditions match" : "Otherwise"}</div>
            {actionNodes(path).length ? column(actionNodes(path)) : <p className="rounded-md border border-dashed border-border bg-card p-2 text-center text-xs text-muted-foreground">End workflow</p>}
          </section>)}
        </div>
      </> : column([...triggerNodes, ...actionNodes("actions")])}
    </div>
  );
}

function CanvasConnector() {
  return <div aria-hidden="true" className="mx-auto flex h-8 w-4 flex-col items-center"><div className="w-px flex-1 bg-primary/60" /><span className="size-2 -translate-y-1 rotate-45 border-r border-b border-primary/70" /></div>;
}
function NodeSettings({ organizationId, graph, update, selection, select, readOnly }: {
  organizationId: string; graph: WorkflowGraph; update: (graph: WorkflowGraph) => void;
  selection: NodeSelection; select: (node: NodeSelection) => void; readOnly: boolean;
}) {
  const conditions = graph.conditions ?? [];
  const field = graph.trigger === "opportunity_stage_changed" ? "opportunity_stage" :
    graph.trigger === "lead_created" || graph.trigger === "lead_status_changed" ? "lead_status" : null;
  const stages = useQuery({ queryKey: ["pipeline-stages", organizationId], queryFn: () => listPipelineStages(organizationId), enabled: field === "opportunity_stage" });
  const values = field === "opportunity_stage" ? (stages.data ?? []).map(({ key, label }) => ({ key, label })) : leadStatuses.map((key) => ({ key, label: key }));
  const path = selection.kind === "action" ? selection.path : "actions";
  const actions = graph[path] ?? [];
  const action = selection.kind === "action" ? actions[selection.index] : undefined;
  const condition = selection.kind === "condition" ? conditions[selection.index] : undefined;
  const actionCount = graph.actions.length + (graph.otherwise_actions?.length ?? 0);
  const [triggerNotice, setTriggerNotice] = useState("");
  const hasApproval = actions.some((entry) => entry.type === "require_approval");
  const selectableActions: WorkflowAction["type"][] = ["create_task"];
  if (field === "lead_status") {
    selectableActions.push("update_lead");
    if (!actions.some((entry) => entry.type === "prepare_follow_up") || action?.type === "prepare_follow_up") selectableActions.push("prepare_follow_up");
  }
  function editAction(next: WorkflowAction) {
    if (selection.kind === "action") update({ ...graph, [path]: actions.map((entry, index) => index === selection.index ? next : entry) });
  }
  function editCondition(next: WorkflowCondition) {
    if (selection.kind === "condition") update({ ...graph, conditions: conditions.map((entry, index) => index === selection.index ? next : entry) });
  }
  function move(offset: number) {
    if (selection.kind === "trigger") return;
    const index = selection.index;
    if (selection.kind === "condition") {
      const reordered = [...conditions];
      [reordered[index], reordered[index + offset]] = [reordered[index + offset], reordered[index]];
      update({ ...graph, conditions: reordered });
    } else {
      const reordered = [...actions];
      [reordered[index], reordered[index + offset]] = [reordered[index + offset], reordered[index]];
      update({ ...graph, [path]: reordered });
    }
    select({ ...selection, index: index + offset });
  }
  function addAction(target: ActionPath, type: WorkflowAction["type"]) {
    const current = graph[target] ?? [];
    const approval = type === "require_approval";
    const action: WorkflowAction = approval ? { type } : { type, title: "Workflow follow-up" };
    const next = approval ? [action, ...current] : [...current, action];
    const withTask = approval && !next.some((entry) => entry.type !== "require_approval")
      ? [...next, { type: "create_task", title: "Workflow follow-up" }]
      : next;
    update({ ...graph, [target]: withTask });
    select({ kind: "action", path: target, index: approval ? 0 : current.length });
  }
  return (
    <>
      <h3 className="text-sm font-semibold">Node configuration</h3>
      {readOnly ? <p className="mt-1 text-xs text-muted-foreground">Pause an active workflow to edit it.</p> : null}
      {selection.kind === "trigger" ? <p className="mt-2 text-xs leading-5 text-muted-foreground">Choose when this workflow starts. A schedule repeats on its own. The other triggers start from a CRM change or from a test on this page.</p> : null}
      {condition ? <p className="mt-2 text-xs leading-5 text-muted-foreground">All or any of these checks decide the path. Matching records follow Conditions match. Everything else follows Otherwise.</p> : null}
      {action?.type === "require_approval" ? <p className="mt-2 text-xs leading-5 text-muted-foreground">The run waits here until an administrator decides. Later actions do not run before that decision. A preview does not request approval.</p> : null}
      {action?.type === "create_task" ? <p className="mt-2 text-xs leading-5 text-muted-foreground">Saves a task on the selected record. A preview shows this step without saving the task.</p> : null}
      <fieldset disabled={readOnly} className="mt-3 grid min-w-0 gap-3">
        {selection.kind === "trigger" ? <>
          <label className="grid gap-1 text-sm">Trigger<TriggerSelect trigger={graph.trigger} onChange={(trigger) => {
            const nextField = trigger === "opportunity_stage_changed" ? "opportunity_stage" :
              trigger === "lead_created" || trigger === "lead_status_changed" ? "lead_status" : null;
            const nextConditions = conditions.filter((entry) => entry.field === nextField);
            if (nextConditions.length !== conditions.length) {
              setTriggerNotice("Remove the current conditions before switching to a different trigger type.");
              return;
            }
            setTriggerNotice("");
            update({ ...graph, trigger });
          }} /></label>
          {triggerNotice ? <p role="status" className="text-xs text-muted-foreground">{triggerNotice}</p> : null}
          {graph.trigger === "schedule" ? <label className="grid gap-1 text-sm">Repeat interval (minutes)<Input type="number" min={1} max={525600} step={1} value={(graph.interval_seconds ?? 3600) / 60} onChange={(e) => update({ ...graph, interval_seconds: Number(e.target.value) * 60 })} /></label> : null}
        </> : null}
        {condition ? <>
          <label className="grid gap-1 text-sm">Match conditions<select className={controlClass} value={graph.condition_mode ?? "all"} onChange={(e) => update({ ...graph, condition_mode: e.target.value as "all" | "any" })}><option value="all">All conditions</option><option value="any">Any condition</option></select></label>
          <label className="grid gap-1 text-sm">Operator<select className={controlClass} value={condition.operator} onChange={(e) => editCondition({ ...condition, operator: e.target.value as WorkflowCondition["operator"] })}><option value="equals">Equals</option><option value="not_equals">Does not equal</option></select></label>
          <label className="grid gap-1 text-sm">{field === "lead_status" ? "Lead status" : "Opportunity stage"}<select className={controlClass} value={condition.value} onChange={(e) => editCondition({ ...condition, value: e.target.value })}>
            {values.map(({ key, label }) => <option key={key} value={key}>{label}</option>)}
          </select></label>
        </> : null}
        {action ? <>
          {action.type !== "require_approval" ? <label className="grid gap-1 text-sm">Action<select className={controlClass} value={action.type} onChange={(e) => editAction({ type: e.target.value as WorkflowAction["type"] })}>
            {!selectableActions.includes(action.type) ? <option value={action.type}>{stepLabels[action.type]} (requires lead trigger)</option> : null}
            {selectableActions.map((type) => <option key={type} value={type}>{stepLabels[type]}</option>)}
          </select></label> : <label className="grid gap-1 text-sm">Reviewer instructions<Textarea value={action.note ?? ""} maxLength={500} onChange={(e) => editAction({ ...action, note: e.target.value })} /></label>}
          {action.type === "create_task" ? <>
            <label className="grid gap-1 text-sm">Task title<Input placeholder="Workflow follow-up" maxLength={200} value={action.title ?? ""} onChange={(e) => editAction({ ...action, title: e.target.value })} /></label>
            <label className="grid gap-1 text-sm">Task description<Textarea maxLength={2000} value={action.description ?? ""} onChange={(e) => editAction({ ...action, description: e.target.value })} /></label>
            <label className="grid gap-1 text-sm">Task priority<select className={controlClass} value={action.priority ?? "normal"} onChange={(event) => editAction({ ...action, priority: event.target.value as WorkflowAction["priority"] })}>
              <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option>
            </select></label>
            <label className="grid gap-1 text-sm">Due after execution (hours)<Input type="number" min={1} max={8760} step={1} placeholder="No deadline" value={action.due_in_hours ?? ""} onChange={(event) => editAction({ ...action, due_in_hours: event.target.value === "" ? undefined : event.target.valueAsNumber })} /></label>
          </> : null}
          {action.type === "update_lead" ? <label className="grid gap-1 text-sm">New status<select className={controlClass} value={action.status ?? ""} onChange={(e) => editAction({ ...action, status: e.target.value })}><option value="">Choose a status</option>{leadStatuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label> : null}
          {action.type === "prepare_follow_up" ? <p className="text-xs text-muted-foreground">Requires a linked contact with an email address, a lead inquiry, and a configured language provider. The draft goes to Approvals.</p> : null}
        </> : null}
        {selection.kind !== "trigger" && !readOnly ? <div className="flex flex-wrap gap-1">
          {(condition || (action && action.type !== "require_approval")) ? <>
            <Button size="sm" variant="outline" aria-label={condition ? "Move condition up" : "Move action up"} disabled={selection.index <= (!condition && hasApproval ? 1 : 0)} onClick={() => move(-1)}><ArrowUp className="size-4" /></Button>
            <Button size="sm" variant="outline" aria-label={condition ? "Move condition down" : "Move action down"} disabled={selection.index >= (condition ? conditions : actions).length - 1} onClick={() => move(1)}><ArrowDown className="size-4" /></Button>
          </> : null}
          <Button size="sm" variant="ghost" onClick={() => {
            if (selection.kind === "action") update({ ...graph, [path]: actions.filter((_, index) => index !== selection.index) });
            else if (conditions.length === 1 && graph.otherwise_actions?.length) return;
            else update({ ...graph, conditions: conditions.filter((_, index) => index !== selection.index) });
            select({ kind: "trigger" });
          }} disabled={Boolean(condition && conditions.length === 1 && graph.otherwise_actions?.length)}>Remove step</Button>
        </div> : null}
        {condition && conditions.length === 1 && graph.otherwise_actions?.length ? (
          <p className="text-xs text-muted-foreground">Remove the otherwise steps before deleting the last condition.</p>
        ) : null}
      </fieldset>
      {!readOnly ? <div className="mt-4 grid gap-2 border-t border-border pt-4">
        {field === "opportunity_stage" && stages.error ? <RequestError error={stages.error} /> : null}
        {field && conditions.length < 5 ? <Button size="sm" variant="outline" disabled={!values.length} onClick={() => {
          update({ ...graph, conditions: [...conditions, { field, operator: "equals", value: values[0].key }] });
          select({ kind: "condition", index: conditions.length });
        }}><GitBranch className="size-4" />Add condition</Button> : null}
        {actionCount < 20 ? <><Button size="sm" variant="outline" onClick={() => addAction("actions", "create_task")}><Plus className="size-4" />{conditions.length ? "Add matched action" : "Add action"}</Button>
        {conditions.length ? <Button size="sm" variant="outline" onClick={() => addAction("otherwise_actions", "create_task")}><Plus className="size-4" />Add otherwise action</Button> : null}
        {!graph.actions.some((entry) => entry.type === "require_approval") ? <Button size="sm" variant="outline" onClick={() => addAction("actions", "require_approval")}><ShieldCheck className="size-4" />Add approval</Button> : null}
        {conditions.length && !(graph.otherwise_actions ?? []).some((entry) => entry.type === "require_approval") ? <Button size="sm" variant="outline" onClick={() => addAction("otherwise_actions", "require_approval")}><ShieldCheck className="size-4" />Add otherwise approval</Button> : null}</> : null}
      </div> : null}
    </>
  );
}
