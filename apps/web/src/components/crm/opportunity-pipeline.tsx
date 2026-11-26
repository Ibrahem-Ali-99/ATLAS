"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { ConfirmButton } from "@/components/confirm-button";
import { RequestError } from "@/components/request-error";
import { Skeleton } from "@/components/ui/skeleton";
import { archiveOpportunity, createOpportunity, createPipelineStage, deletePipelineStage, listOpportunities, listPipelineStages, reorderPipelineStages, restoreOpportunity, updateOpportunity, type Opportunity } from "@/lib/opportunities";
import { listOpportunityTasks, createOpportunityTask, updateWorkflowTask, type WorkflowTask } from "@/lib/workflow-definitions";
import { listTeam } from "@/lib/organization";
import { listCompanies, listContacts, listLeads } from "@/lib/records-api";
import { useWorkspace } from "@/lib/use-workspace";

export function OpportunityPipeline({ selectedId, onSelect }: {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { organizationId, role } = useWorkspace();
  const client = useQueryClient();
  const id = organizationId ?? "";
  const stages = useQuery({ queryKey: ["pipeline-stages", id], queryFn: () => listPipelineStages(id), enabled: Boolean(id) });
  const [includeArchived, setIncludeArchived] = useState(false);
  const opportunities = useQuery({ queryKey: ["opportunities", id, includeArchived], queryFn: () => listOpportunities(id, includeArchived), enabled: Boolean(id) });
  const [title, setTitle] = useState("");
  const [stageName, setStageName] = useState("");
  const selected = opportunities.data?.find((item) => item.id === selectedId);
  const refresh = () => void client.invalidateQueries({ queryKey: ["opportunities", id] });
  const refreshStages = () => void client.invalidateQueries({ queryKey: ["pipeline-stages", id] });
  const save = useMutation({
    mutationFn: ({ opportunityId, body }: { opportunityId: string; body: Record<string, unknown> }) => updateOpportunity(id, opportunityId, body),
    onSuccess: refresh,
  });
  const create = useMutation({
    mutationFn: (stage: string) => createOpportunity(id, { title: title.trim(), stage }),
    onSuccess: (item) => { setTitle(""); refresh(); onSelect(item.id); },
  });
  const move = useMutation({
    mutationFn: ({ item, stage }: { item: Opportunity; stage: string }) => updateOpportunity(id, item.id, { stage }),
    onSuccess: refresh,
  });
  const archive = useMutation({
    mutationFn: (opportunityId: string) => archiveOpportunity(id, opportunityId),
    onSuccess: () => { refresh(); onSelect(null); },
  });
  const restore = useMutation({
    mutationFn: (opportunityId: string) => restoreOpportunity(id, opportunityId),
    onSuccess: refresh,
  });
  const addStage = useMutation({
    mutationFn: () => createPipelineStage(id, { label: stageName.trim(), position: stages.data?.length ?? 0 }),
    onSuccess: () => { setStageName(""); refreshStages(); },
  });
  const removeStage = useMutation({ mutationFn: (stage: string) => deletePipelineStage(id, stage), onSuccess: refreshStages });
  if (stages.isPending || opportunities.isPending) return <Skeleton className="h-48 w-full" />;
  if (stages.isError || opportunities.isError) return <RequestError error={stages.error ?? opportunities.error} />;
  const items = opportunities.data ?? [];
  const columns = stages.data ?? [];
  const firstStage = columns[0]?.key;
  const error = create.error ?? move.error ?? addStage.error ?? removeStage.error ?? archive.error ?? restore.error;
  return (
    <section className="min-w-0 rounded-xl border border-border bg-card p-4 sm:p-5" aria-label="Sales pipeline" data-testid="sales-pipeline">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold">Sales pipeline</h2>
          <p className="mt-1 text-sm text-muted-foreground">Open an opportunity to edit it, drag it, or move it to the next stage.</p>
        </div>
        <form className="flex w-full min-w-0 gap-2 sm:w-auto" onSubmit={(event) => {
          event.preventDefault();
          if (firstStage && title.trim() && !create.isPending) create.mutate(firstStage);
        }}>
          <Input aria-label="New opportunity title" placeholder="New opportunity" className="min-w-0" maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} />
          <Button type="submit" disabled={!firstStage || !title.trim() || create.isPending}>{create.isPending ? "Creating…" : "Create"}</Button>
        </form>
        <label className="flex items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} /> Show archived, excluded from analytics</label>
      </div>
      {error ? <div className="mt-3"><RequestError error={error} /></div> : null}
      {!items.length ? <p className="mt-4 rounded-lg border border-dashed border-border p-3 text-sm text-muted-foreground">No opportunities yet. Add one to start tracking your pipeline.</p> : null}
      <div className="mt-4 grid min-w-0 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
        {columns.map((stage) => {
          const matching = items.filter((item) => item.stage === stage.key);
          return (
            <section key={stage.key} className="min-w-0 rounded-lg bg-muted/60 p-3" aria-label={stage.label}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                const item = items.find((candidate) => candidate.id === event.dataTransfer.getData("text/opportunity"));
                if (item && !item.archived_at && item.stage !== stage.key && !move.isPending) move.mutate({ item, stage: stage.key });
              }}>
              <div className="flex items-center justify-between gap-2">
                <h3 className="min-w-0 break-words text-xs font-semibold uppercase tracking-wide text-muted-foreground">{stage.label}</h3>
                <span className="rounded-full bg-background px-2 py-0.5 text-xs">{matching.length}</span>
              </div>
              <ul className="mt-2 space-y-2">
                {matching.map((item) => {
                  const index = columns.findIndex((column) => column.key === item.stage);
                  const previous = index > 0 ? columns[index - 1] : undefined;
                  const next = index >= 0 && index < columns.length - 1 ? columns[index + 1] : undefined;
                  return <li key={item.id}>
                  <button type="button" draggable={!move.isPending && !item.archived_at} onDragStart={(event) => event.dataTransfer.setData("text/opportunity", item.id)}
                    onClick={() => onSelect(item.id)} className="block w-full cursor-pointer rounded-md border border-border bg-card p-3 text-left shadow-sm hover:border-primary/50">
                    <span className="block break-words text-sm font-medium">{item.title}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">{item.value == null ? "Value not set" : `${item.currency} ${item.value.toLocaleString()}`}</span>
                    {item.expected_close_date ? <span className="mt-1 block text-xs text-muted-foreground">Close {new Date(item.expected_close_date).toLocaleDateString()}</span> : null}
                    {item.archived_at ? <span className="mt-1 block text-xs text-muted-foreground">Archived</span> : null}
                  </button>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {item.archived_at ? <button type="button" className="rounded border border-border bg-card px-2 py-1 text-[11px]" disabled={restore.isPending} onClick={() => restore.mutate(item.id)}>Restore</button> : null}
                    {!item.archived_at && previous ? <button type="button" className="rounded border border-border bg-card px-2 py-1 text-[11px]" disabled={move.isPending} onClick={() => move.mutate({ item, stage: previous.key })}>Move to {previous.label}</button> : null}
                    {!item.archived_at && next ? <button type="button" className="rounded border border-border bg-card px-2 py-1 text-[11px]" disabled={move.isPending} onClick={() => move.mutate({ item, stage: next.key })}>Move to {next.label}</button> : null}
                  </div>
                </li>;
                })}
              </ul>
              {!matching.length ? <p className="mt-3 text-xs text-muted-foreground">No opportunities</p> : null}
            </section>
          );
        })}
      </div>
      {role === "admin" ? <details className="mt-4 border-t border-border pt-3">
        <summary className="cursor-pointer text-sm font-medium">Pipeline settings</summary>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <StageReorderControls organizationId={id} stages={columns} onSaved={refreshStages} />
          <Input aria-label="New pipeline stage" className="max-w-48" placeholder="Stage name" maxLength={80} value={stageName} onChange={(event) => setStageName(event.target.value)} />
          <Button size="sm" variant="outline" disabled={!stageName.trim() || addStage.isPending} onClick={() => addStage.mutate()}>Add stage</Button>
          {columns.filter((stage) => !items.some((item) => item.stage === stage.key)).map((stage) => (
            <ConfirmButton key={stage.key} size="sm" label={`Remove ${stage.label}`} confirmLabel={`Confirm removal of ${stage.label}`} pendingLabel="Removing…" pending={removeStage.isPending} onConfirm={() => removeStage.mutate(stage.key)} />
          ))}
        </div>
      </details> : null}
      <Dialog open={Boolean(selected)} onOpenChange={(open) => { if (!open) onSelect(null); }}>
        {selected ? <DialogContent className="max-h-[85dvh] max-w-2xl overflow-y-auto">
          <DialogTitle className="break-words">{selected.title}</DialogTitle>
          <DialogDescription>{selected.archived_at ? "This opportunity is archived and is left out of pipeline metrics." : "Update this opportunity and manage its follow-up tasks."}</DialogDescription>
          {selected.archived_at ? (
            <Button type="button" variant="outline" disabled={restore.isPending} onClick={() => restore.mutate(selected.id)}>{restore.isPending ? "Restoring…" : "Restore opportunity"}</Button>
          ) : (
            <>
              <OpportunityEditor key={selected.id} organizationId={id} opportunity={selected} stages={columns} onClose={() => onSelect(null)}
                onSave={(body) => save.mutate({ opportunityId: selected.id, body }, { onSuccess: () => onSelect(null) })} saving={save.isPending} />
              <div className="mt-3"><ConfirmButton label="Archive opportunity" confirmLabel="Confirm archive" pendingLabel="Archiving…" pending={archive.isPending} onConfirm={() => archive.mutate(selected.id)} /></div>
            </>
          )}
          {save.error ? <div className="mt-3"><RequestError error={save.error} /></div> : null}
        </DialogContent> : null}
      </Dialog>
      {selectedId && !selected && !create.isPending && !opportunities.isFetching ? <div className="mt-4 rounded-lg border border-border p-3">
        <p className="text-sm">This opportunity is unavailable.</p><Button className="mt-2" size="sm" variant="outline" onClick={() => onSelect(null)}>Clear selection</Button>
      </div> : null}
    </section>
  );
}

function OpportunityEditor({ organizationId, opportunity, stages, onClose, onSave, saving }: { organizationId: string; opportunity: Opportunity; stages: { key: string; label: string }[]; onClose: () => void; onSave: (body: Record<string, unknown>) => void; saving: boolean }) { const [name, setName] = useState(opportunity.title); const [value, setValue] = useState(opportunity.value?.toString() ?? ""); const [currency, setCurrency] = useState(opportunity.currency); const [probability, setProbability] = useState(opportunity.probability?.toString() ?? ""); const [stage, setStage] = useState(opportunity.stage); const [closeDate, setCloseDate] = useState(opportunity.expected_close_date?.slice(0, 10) ?? ""); const [lossReason, setLossReason] = useState(opportunity.loss_reason ?? ""); const [taskTitle, setTaskTitle] = useState(""); const [taskPriority, setTaskPriority] = useState("normal"); const [taskDue, setTaskDue] = useState(""); const [owner, setOwner] = useState(opportunity.owner_user_id); const [contact, setContact] = useState(opportunity.contact_id ?? ""); const [company, setCompany] = useState(opportunity.company_id ?? ""); const [lead, setLead] = useState(opportunity.lead_id ?? ""); const tasks = useQuery({ queryKey: ["opportunity-tasks", organizationId, opportunity.id], queryFn: () => listOpportunityTasks(organizationId, opportunity.id) }); const team = useQuery({ queryKey: ["team", organizationId], queryFn: () => listTeam(organizationId) }); const contacts = useQuery({ queryKey: ["contacts", organizationId], queryFn: () => listContacts(organizationId, { pageSize: 100 }) }); const companies = useQuery({ queryKey: ["companies", organizationId], queryFn: () => listCompanies(organizationId, { pageSize: 100 }) }); const leads = useQuery({ queryKey: ["leads", organizationId], queryFn: () => listLeads(organizationId, { pageSize: 100 }) }); const taskCreate = useMutation({ mutationFn: () => createOpportunityTask(organizationId, opportunity.id, { title: taskTitle.trim(), priority: taskPriority, due_at: taskDue ? `${taskDue}T00:00:00Z` : null }), onSuccess: () => { setTaskTitle(""); setTaskDue(""); void tasks.refetch(); } }); const selectClass = "mt-1 h-9 w-full rounded border border-input bg-background px-2 text-sm"; return <div className="mt-4 rounded-lg border border-primary/30 bg-background p-4" aria-label="Opportunity details"><div className="flex items-center justify-between"><h3 className="font-semibold">Opportunity details</h3><button type="button" className="text-sm text-muted-foreground" onClick={onClose}>Close</button></div><div className="mt-3 grid gap-3 sm:grid-cols-2">{[["Name", name, setName], ["Value", value, setValue], ["Currency", currency, setCurrency], ["Probability", probability, setProbability]] .map(([label, current, setter]) => <label key={label as string} className="text-xs">{label as string}<input className={selectClass} value={current as string} onChange={(e) => (setter as (value: string) => void)(e.target.value)} /></label>)}<label className="text-xs">Stage<select className={selectClass} value={stage} onChange={(e) => setStage(e.target.value)}>{stages.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label><label className="text-xs">Owner<select className={selectClass} value={owner} onChange={(e) => setOwner(e.target.value)}><option value="">Unassigned</option>{(team.data ?? []).filter((item) => item.is_active).map((item) => <option key={item.user_id} value={item.user_id}>{item.full_name}</option>)}</select></label><label className="text-xs">Contact<select className={selectClass} value={contact} onChange={(e) => setContact(e.target.value)}><option value="">None</option>{(contacts.data?.items ?? []).map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}</select></label><label className="text-xs">Company<select className={selectClass} value={company} onChange={(e) => setCompany(e.target.value)}><option value="">None</option>{(companies.data?.items ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="text-xs">Lead<select className={selectClass} value={lead} onChange={(e) => setLead(e.target.value)}><option value="">None</option>{(leads.data?.items ?? []).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><label className="text-xs">Expected close date<input type="date" className={selectClass} value={closeDate} onChange={(e) => setCloseDate(e.target.value)} /></label></div>{stage === "lost" ? <label className="mt-3 block text-xs">Loss reason<textarea className="mt-1 min-h-16 w-full rounded border border-input bg-background px-2 py-1 text-sm" value={lossReason} onChange={(e) => setLossReason(e.target.value)} required /></label> : null}<div className="mt-4 flex justify-end gap-2"><button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm" onClick={onClose}>Cancel</button><button type="button" className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50" disabled={!name.trim() || (stage === "lost" && !lossReason.trim()) || saving} onClick={() => onSave({ title: name, value: value ? Number(value) : null, currency, probability: probability ? Number(probability) : null, stage, expected_close_date: closeDate ? `${closeDate}T00:00:00Z` : null, loss_reason: stage === "lost" ? lossReason : null, owner_user_id: owner || null, contact_id: contact || null, company_id: company || null, lead_id: lead || null })}>Save changes</button></div><div className="mt-5 border-t border-border pt-4"><h4 className="text-sm font-semibold">Linked tasks</h4><div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_7rem_9rem_auto]"><input aria-label="New opportunity task" className="h-8 rounded border border-input bg-background px-2 text-sm" value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} placeholder="Add a task" /><select aria-label="Opportunity task priority" className="h-8 rounded border border-input bg-background px-2 text-xs" value={taskPriority} onChange={(e) => setTaskPriority(e.target.value)}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select><input aria-label="Opportunity task deadline" type="date" className="h-8 rounded border border-input bg-background px-2 text-xs" value={taskDue} onChange={(e) => setTaskDue(e.target.value)} /><button type="button" className="rounded border border-border px-2 text-xs" disabled={!taskTitle.trim() || taskCreate.isPending} onClick={() => taskCreate.mutate()}>Add</button></div><div className="mt-2 space-y-1">{(tasks.data ?? []).map((task: WorkflowTask) => <div key={task.id} className="flex items-center justify-between gap-2 text-xs"><span>{task.title} · {task.priority}{task.due_at ? ` · due ${new Date(task.due_at).toLocaleDateString()}` : ""}</span><select aria-label={`Status for ${task.title}`} value={task.status} onChange={(e) => void updateWorkflowTask(organizationId, task.id, e.target.value).then(() => tasks.refetch())}><option value="open">To Do</option><option value="in_progress">In Progress</option><option value="completed">Completed</option></select></div>)}</div></div></div>; }

function StageReorderControls({ organizationId, stages, onSaved }: { organizationId: string; stages: { key: string; label: string }[]; onSaved: () => void }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function move(index: number, direction: -1 | 1) {
    const next = [...stages];
    const target = index + direction;
    if (!next[index] || !next[target] || saving) return;
    [next[index], next[target]] = [next[target], next[index]];
    setSaving(true); setError("");
    try { await reorderPipelineStages(organizationId, next.map((item) => item.key)); onSaved(); }
    catch (err) { setError(err instanceof Error ? err.message : "Stage order could not be saved."); }
    finally { setSaving(false); }
  }
  return <div className="flex flex-wrap gap-1" aria-label="Reorder pipeline stages">{stages.map((stage, index) => <span key={stage.key} className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs"><span>{stage.label}</span><button type="button" aria-label={`Move ${stage.label} up`} disabled={saving || index === 0} onClick={() => void move(index, -1)}>↑</button><button type="button" aria-label={`Move ${stage.label} down`} disabled={saving || index === stages.length - 1} onClick={() => void move(index, 1)}>↓</button></span>)}{saving ? <span role="status">Saving…</span> : null}{error ? <span role="alert">{error}</span> : null}</div>;
}
