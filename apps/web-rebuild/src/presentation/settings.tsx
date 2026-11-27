import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Building2, Check, Clock3, Laptop, LockKeyhole, Mail, Monitor, MoreHorizontal, Palette, Plus, Search, ShieldCheck, Trash2, UserRound, Users } from "lucide-react";
import { changeMemberRole, failureMessage, inviteMember, loadInvitations, loadOnboarding, loadTeam, removeTeamMember, renameOrganization, saveOnboarding } from "@/data/resources";
import { appConfig } from "./appConfig";
import { Avatar, Badge, Button, Modal } from "./components";

type Section = "Organization" | "Account" | "Members" | "Sessions";
type Member = { id: string; name: string; email: string; initials: string; role: "Admin" | "Staff"; status: "Active" | "Pending"; self?: boolean; pending?: boolean };

export function SettingsWorkspace({ onToast, onSessionExpired }: { onToast: (message: string) => void; onSessionExpired: () => void }) {
  const [section, setSection] = useState<Section>("Organization");
  const [members, setMembers] = useState<Member[]>([]);
  const [organizationName, setOrganizationName] = useState(appConfig.organization.name);
  const [timezone, setTimezone] = useState("UTC");
  const [industry, setIndustry] = useState("");
  const [description, setDescription] = useState("");
  const [issuedToken, setIssuedToken] = useState("");
  const [search, setSearch] = useState("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [confirmAction, setConfirmAction] = useState<null | { type: "remove" | "sessions" | "leave"; member?: Member }>(null);
  const filtered = useMemo(() => members.filter((member) => `${member.name} ${member.email}`.toLowerCase().includes(search.toLowerCase())), [members, search]);
  const refresh = () => Promise.all([loadTeam(), loadInvitations()]).then(([team, invitations]) => {
    const people: Member[] = team.map((member) => ({ id: member.membership_id, name: member.full_name, email: member.email, initials: member.full_name.slice(0, 2).toUpperCase(), role: member.role === "admin" ? "Admin" : "Staff", status: "Active", self: member.email === appConfig.user.email }));
    const pending: Member[] = invitations.filter((item) => !item.accepted_at).map((item) => ({ id: item.id, name: item.email, email: item.email, initials: item.email.slice(0, 2).toUpperCase(), role: "Staff", status: "Pending", pending: true }));
    setMembers([...people, ...pending]);
  });
  useEffect(() => {
    refresh().catch((error: unknown) => onToast(failureMessage(error)));
    loadOnboarding().then((state) => { setOrganizationName(state.organization.name); setTimezone(state.setup.timezone); setIndustry(state.setup.industry || ""); setDescription(state.setup.business_description || ""); }).catch(() => undefined);
  }, [onToast]);
  const invite = () => {
    void inviteMember(inviteEmail).then((created) => { setIssuedToken(created.token); setInviteEmail(""); onToast("Invitation created"); return refresh(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const confirm = () => {
    if (confirmAction?.type === "remove" && confirmAction.member && !confirmAction.member.pending) {
      void removeTeamMember(confirmAction.member.id).then(() => { onToast("Member removed"); return refresh(); }).catch((error: unknown) => onToast(failureMessage(error)));
    } else if (confirmAction?.type === "sessions") {
      setConfirmAction(null); onSessionExpired(); return;
    } else onToast("Leaving the organization is not available from this screen.");
    setConfirmAction(null);
  };
  const saveOrganization = () => {
    void renameOrganization(organizationName).then(() => saveOnboarding({ timezone, industry, business_description: description })).then(() => onToast("Organization saved")).catch((error: unknown) => onToast(failureMessage(error)));
  };
  return <main className="module-main settings-main">
    <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Workspace administration</div><h1>Settings</h1><p>Manage organization, account, members, and local sessions.</p></div><Badge tone="purple"><ShieldCheck size={13} /> Administrator</Badge></div>
    <div className="settings-layout">
      <nav className="settings-nav" aria-label="Settings sections">{(["Organization", "Account", "Members", "Sessions"] as Section[]).map((item) => { const Icon = item === "Organization" ? Building2 : item === "Account" ? UserRound : item === "Members" ? Users : Laptop; return <button key={item} className={section === item ? "active" : ""} onClick={() => setSection(item)}><Icon size={15} />{item}</button>; })}</nav>
      <div className="settings-content">
        {section === "Organization" && <>
          <SettingsHeading title="Organization details" copy="Basic workspace identity and regional preferences." />
          <section className="settings-card"><div className="settings-card-body form-stack"><label className="field"><span>Organization name</span><input value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} /></label><label className="field"><span>Workspace identifier</span><input value={appConfig.organization.slug || organizationName} disabled /><small>The workspace identifier is assigned by the organization record.</small></label><label className="field"><span>Industry</span><input value={industry} onChange={(event) => setIndustry(event.target.value)} /></label><label className="field"><span>Business description</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label><div className="field-row"><label className="field"><span>Time zone</span><input value={timezone} onChange={(event) => setTimezone(event.target.value)} /></label></div></div><div className="settings-card-footer"><Button variant="primary" onClick={saveOrganization}><Check size={14} /> Save changes</Button></div></section>
          <section className="settings-card danger-zone"><div><strong>Leave organization</strong><p>Administrators cannot leave the only locally available organization.</p></div><Button variant="danger" onClick={() => setConfirmAction({ type: "leave" })}>Leave organization</Button></section>
        </>}
        {section === "Account" && <>
          <SettingsHeading title="Profile and appearance" copy="Update your local profile and interface preferences." />
          <section className="settings-card"><div className="settings-card-body"><div className="profile-edit"><Avatar initials={appConfig.user.initials} tone="blue" /><div><strong>{appConfig.user.name}</strong><small>Signed-in account</small></div></div><div className="field-row"><label className="field"><span>Full name</span><input value={appConfig.user.name} disabled /></label><label className="field"><span>Email</span><input value={appConfig.user.email} disabled /></label></div></div></section>
          <section className="settings-card"><div className="settings-card-title"><Palette size={17} /><div><strong>Appearance</strong><p>Theme preference follows the control in the workspace header.</p></div></div><div className="appearance-options"><button className="active"><Monitor size={17} /> Current theme</button><button disabled><Palette size={17} /> Custom theme <Badge>Unavailable</Badge></button></div></section>
        </>}
        {section === "Members" && <>
          <div className="settings-heading-row"><SettingsHeading title="Members and invitations" copy="Admins can invite members and adjust supported roles." /><Button variant="primary" onClick={() => setInviteOpen(true)}><Plus size={15} /> Invite member</Button></div>
          <div className="member-tools"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search members" /></label><Badge>{members.filter((member) => member.status === "Pending").length} pending</Badge></div>
          <section className="settings-card member-list">{filtered.length ? filtered.map((member) => <div className="member-row" key={member.email}><Avatar initials={member.initials} tone={member.status === "Pending" ? "amber" : "blue"} /><span><strong>{member.name}{member.self ? " (you)" : ""}</strong><small>{member.email}</small></span><Badge tone={member.status === "Pending" ? "amber" : "green"}>{member.status}</Badge><select aria-label={`Role for ${member.name}`} value={member.role} disabled={member.self || member.pending} onChange={(event) => { const role = event.target.value === "Admin" ? "admin" : "staff"; void changeMemberRole(member.id, role).then(() => refresh()).catch((error: unknown) => onToast(failureMessage(error))); }}><option>Admin</option><option>Staff</option></select>{member.self ? <Button size="icon" variant="ghost" disabled aria-label="Current member cannot be removed"><LockKeyhole size={15} /></Button> : member.status === "Pending" ? <Button size="sm" onClick={() => onToast("Invitation reminder unavailable without email delivery")}>Resend</Button> : <Button size="icon" variant="ghost" aria-label={`Remove ${member.name}`} onClick={() => setConfirmAction({ type: "remove", member })}><Trash2 size={15} /></Button>}</div>) : <div className="module-empty compact"><Users size={22} /><strong>No members found</strong><p>Clear the search to see organization members.</p></div>}</section>
        </>}
        {section === "Sessions" && <>
          <SettingsHeading title="Session controls" copy="Ending the session signs this browser out of the workspace." />
          <section className="settings-card"><div className="session-row"><span className="session-icon"><Laptop size={17} /></span><span><strong>Current browser</strong><small>{appConfig.user.email}</small></span><Badge tone="green">Current</Badge></div><div className="settings-card-footer"><Button variant="danger" onClick={() => setConfirmAction({ type: "sessions" })}>End session</Button></div></section>
        </>}
      </div>
    </div>
    <Modal open={inviteOpen} title="Invite member" description="Create a staff invitation for this organization." onClose={() => { setInviteOpen(false); setIssuedToken(""); }}><div className="dialog-body"><label className="field"><span>Email address</span><input autoFocus type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} placeholder="name@organization.example" /></label>{issuedToken && <label className="field"><span>Acceptance token</span><input readOnly value={issuedToken} aria-label="Invitation token" /><small>Shown once. Email delivery follows the workspace mail settings.</small></label>}<div className="permission-state"><Mail size={16} /><span><strong>Staff invitation</strong><small>The API records a staff invitation.</small></span></div></div><div className="dialog-footer"><Button onClick={() => { setInviteOpen(false); setIssuedToken(""); }}>Close</Button><Button variant="primary" disabled={!inviteEmail.includes("@")} onClick={invite}>Create invitation</Button></div></Modal>
    <Modal open={!!confirmAction} title={confirmAction?.type === "remove" ? "Remove member?" : confirmAction?.type === "sessions" ? "End this session?" : "Leave organization?"} description="Review this operation before continuing." onClose={() => setConfirmAction(null)}><div className="dialog-body"><div className="review-callout"><AlertCircle size={17} /><span><strong>This action requires confirmation</strong><p>{confirmAction?.type === "remove" ? `${confirmAction.member?.name} will lose access to this organization.` : confirmAction?.type === "sessions" ? "This browser will be signed out." : "Leaving the organization is not available from this screen."}</p></span></div></div><div className="dialog-footer"><Button onClick={() => setConfirmAction(null)}>Cancel</Button><Button variant="danger" disabled={confirmAction?.type === "leave"} onClick={confirm}>{confirmAction?.type === "remove" ? "Remove member" : confirmAction?.type === "sessions" ? "End session" : "Unavailable"}</Button></div></Modal>
  </main>;
}

function SettingsHeading({ title, copy }: { title: string; copy: string }) { return <div className="settings-heading"><h2>{title}</h2><p>{copy}</p></div>; }
