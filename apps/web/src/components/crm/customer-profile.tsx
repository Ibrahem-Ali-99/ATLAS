"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { getCustomerProfile, type CustomerProfileData } from "@/lib/records-api";
import { listTeam } from "@/lib/organization";
import { createWorkflowTask, updateWorkflowTask } from "@/lib/workflow-definitions";

type Navigate = (target: {
  tab: "companies" | "contacts" | "leads" | "inquiries" | "opportunities";
  id: string | null;
}) => void;

const kindLabels: Record<string, string> = {
  note: "Note",
  call: "Call",
  email: "Email",
  request: "Request",
  appointment: "Appointment",
  task: "Task",
  conversation: "Conversation",
};

export function CustomerProfile({
  organizationId,
  companyId,
  contactId,
  leadId,
  onNavigate,
  hideNotes = false,
}: {
  organizationId: string;
  companyId?: string;
  contactId?: string;
  leadId?: string;
  onNavigate: Navigate;
  hideNotes?: boolean;
}) {
  const client = useQueryClient();
  const profile = useQuery({
    queryKey: ["customer-profile", organizationId, companyId, contactId, leadId],
    queryFn: () => getCustomerProfile(organizationId, { companyId, contactId, leadId }),
  });
  const refresh = () => void client.invalidateQueries({ queryKey: ["customer-profile", organizationId] });
  const complete = useMutation({
    mutationFn: (taskId: string) => updateWorkflowTask(organizationId, taskId, "completed"),
    onSuccess: refresh,
  });
  if (profile.isPending) return <Skeleton className="mt-4 h-24 w-full" />;
  if (profile.isError) return <div className="mt-4"><RequestError error={profile.error} /></div>;
  const data = profile.data;
  const activity = hideNotes
    ? data.activity.filter((item) => !["note", "call", "email"].includes(item.kind))
    : data.activity;
  return (
    <section className="mt-4 space-y-4 border-t border-border pt-4" data-testid="customer-profile">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" asChild>
          <Link href={`/assistant?prompt=${encodeURIComponent(assistantPrompt(data))}`}>Ask the assistant</Link>
        </Button>
        {leadId ? (
          <Button size="sm" variant="outline" asChild>
            <Link href={`/assistant?prompt=${encodeURIComponent(`Draft a follow-up for ${data.subject.title}`)}`}>Draft a follow-up</Link>
          </Button>
        ) : null}
      </div>
      <ProfileList title="Companies" empty="No company is linked." items={data.companies} onOpen={(id) => onNavigate({ tab: "companies", id })} />
      <ProfileList title="Contacts" empty="No contacts are linked." items={data.contacts} onOpen={(id) => onNavigate({ tab: "contacts", id })} />
      <ProfileList title="Leads" empty="No leads are linked." items={data.leads} onOpen={(id) => onNavigate({ tab: "leads", id })} />
      <ProfileList title="Requests" empty="No requests are linked." items={data.inquiries} onOpen={(id) => onNavigate({ tab: "inquiries", id })} />
      <div>
        <h3 className="text-sm font-medium">Opportunities</h3>
        {data.opportunities.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No opportunities are linked.</p> : (
          <ul className="mt-2 space-y-1 text-sm">
            {data.opportunities.map((item) => (
              <li key={item.id}>
                <button type="button" className="text-left text-primary underline" onClick={() => onNavigate({ tab: "opportunities", id: item.id })}>
                  {item.title}
                </button>
                <span className="text-muted-foreground"> · {item.stage.replaceAll("_", " ")}{item.value == null ? "" : ` · ${item.value.toLocaleString()}`}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="text-sm font-medium">Conversations</h3>
        {data.conversations.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No conversations are linked.</p> : (
          <ul className="mt-2 space-y-1 text-sm">
            {data.conversations.map((item) => (
              <li key={item.id}>
                <Link className="text-primary underline" href={`/inbox?conversation=${item.id}`}>{item.subject || item.channel}</Link>
                <span className="text-muted-foreground"> · {item.channel} · {item.status.replaceAll("_", " ")}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="text-sm font-medium">Appointments</h3>
        {data.appointments.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No appointments are stored.</p> : (
          <ul className="mt-2 space-y-1 text-sm">
            {data.appointments.map((item) => (
              <li key={item.id}>
                <button type="button" className="text-left text-primary underline" onClick={() => onNavigate({ tab: "leads", id: item.lead_id })}>
                  {new Date(item.starts_at).toLocaleString()}
                </button>
                <span className="text-muted-foreground"> · {item.status.replaceAll("_", " ")}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="text-sm font-medium">Tasks</h3>
        {complete.isError ? <div className="mt-2"><RequestError error={complete.error} /></div> : null}
        {data.tasks.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No follow-up tasks yet.</p> : (
          <ul className="mt-2 space-y-2 text-sm">
            {data.tasks.map((item) => (
              <li key={item.id} className="rounded-md border border-border p-2">
                <p className="font-medium">{item.title}</p>
                <p className="text-muted-foreground">{item.status.replaceAll("_", " ")} · {item.priority}{item.assignee ? ` · ${item.assignee}` : ""}{item.due_at ? ` · due ${new Date(item.due_at).toLocaleDateString()}` : ""}</p>
                {item.status !== "completed" ? (
                  <Button className="mt-2" type="button" size="sm" variant="outline" disabled={complete.isPending} onClick={() => complete.mutate(item.id)}>Complete</Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {leadId || contactId ? <FollowUp organizationId={organizationId} leadId={leadId} contactId={contactId} onCreated={refresh} /> : null}
      </div>
      <div>
        <h3 className="text-sm font-medium">Activity</h3>
        {activity.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No activity is recorded yet.</p> : (
          <ol className="mt-2 space-y-3">
            {activity.map((item, index) => (
              <li key={`${item.record_kind}-${item.record_id}-${item.at}-${index}`} className="text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{kindLabels[item.kind] ?? item.title}</span>
                  <time className="text-xs text-muted-foreground">{new Date(item.at).toLocaleString()}</time>
                </div>
                <p className="text-muted-foreground">{item.kind === "note" || item.kind === "call" || item.kind === "email" ? item.detail : item.title}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function assistantPrompt(data: CustomerProfileData) {
  if (data.subject.kind === "lead") return `Summarize the lead ${data.subject.title}`;
  if (data.subject.kind === "contact") return `Summarize the contact ${data.subject.title}`;
  return `Summarize the customer ${data.subject.title}`;
}

function ProfileList({
  title,
  empty,
  items,
  onOpen,
}: {
  title: string;
  empty: string;
  items: { id: string; title: string; detail: string | null }[];
  onOpen: (id: string) => void;
}) {
  return (
    <div>
      <h3 className="text-sm font-medium">{title}</h3>
      {items.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">{empty}</p> : (
        <ul className="mt-2 space-y-1 text-sm">
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" className="text-left text-primary underline" onClick={() => onOpen(item.id)}>{item.title}</button>
              {item.detail ? <span className="text-muted-foreground"> · {item.detail}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FollowUp({
  organizationId,
  leadId,
  contactId,
  onCreated,
}: {
  organizationId: string;
  leadId?: string;
  contactId?: string;
  onCreated: () => void;
}) {
  const team = useQuery({ queryKey: ["team", organizationId], queryFn: () => listTeam(organizationId) });
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("normal");
  const [due, setDue] = useState("");
  const [assignee, setAssignee] = useState("");
  const create = useMutation({
    mutationFn: () => createWorkflowTask(organizationId, {
      title: title.trim(),
      priority,
      due_at: due ? `${due}T00:00:00Z` : undefined,
      lead_id: leadId,
      contact_id: contactId,
      assignee_user_id: assignee || undefined,
    }),
    onSuccess: () => {
      setTitle("");
      setDue("");
      onCreated();
    },
  });
  return (
    <form className="mt-3 grid gap-2" onSubmit={(event) => { event.preventDefault(); if (title.trim()) create.mutate(); }}>
      <Input aria-label="Follow-up task" placeholder="Follow-up task" value={title} onChange={(event) => setTitle(event.target.value)} />
      <div className="grid gap-2 sm:grid-cols-3">
        <select aria-label="Task priority" className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={priority} onChange={(event) => setPriority(event.target.value)}>
          <option value="low">Low</option>
          <option value="normal">Normal</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select>
        <Input aria-label="Task deadline" type="date" value={due} onChange={(event) => setDue(event.target.value)} />
        <select aria-label="Assign task" className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={assignee} onChange={(event) => setAssignee(event.target.value)}>
          <option value="">Assign to me</option>
          {(team.data ?? []).filter((item) => item.is_active).map((item) => (
            <option key={item.user_id} value={item.user_id}>{item.full_name}</option>
          ))}
        </select>
      </div>
      {create.isError ? <RequestError error={create.error} /> : null}
      <Button type="submit" size="sm" variant="outline" disabled={!title.trim() || create.isPending}>{create.isPending ? "Adding…" : "Add task"}</Button>
    </form>
  );
}
