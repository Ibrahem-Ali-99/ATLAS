import { useMemo, useState } from "react";
import { AlertCircle, Building2, Check, Clock3, Laptop, LockKeyhole, Mail, Monitor, MoreHorizontal, Palette, Plus, Search, ShieldCheck, Trash2, UserRound, Users } from "lucide-react";
import { appConfig } from "./appConfig";
import { Avatar, Badge, Button, Modal } from "./components";

type Section = "Organization" | "Account" | "Members" | "Sessions";
type Member = { name: string; email: string; initials: string; role: "Admin" | "Staff"; status: "Active" | "Pending"; self?: boolean };
const initialMembers: Member[] = [
  { name: appConfig.user.name, email: appConfig.user.email, initials: appConfig.user.initials, role: "Admin", status: "Active", self: true },
  { name: "Sam Rivera", email: "sam@harborandco.example", initials: "SR", role: "Staff", status: "Active" },
  { name: "Maya Chen", email: "maya@harborandco.example", initials: "MC", role: "Staff", status: "Active" },
  { name: "Jordan Lee", email: "jordan@harborandco.example", initials: "JL", role: "Staff", status: "Pending" },
];

export function SettingsWorkspace({ onToast, onSessionExpired }: { onToast: (message: string) => void; onSessionExpired: () => void }) {
  const [section, setSection] = useState<Section>("Organization");
  const [members, setMembers] = useState(initialMembers);
  const [search, setSearch] = useState("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"Admin" | "Staff">("Staff");
  const [confirmAction, setConfirmAction] = useState<null | { type: "remove" | "sessions" | "leave"; member?: Member }>(null);
  const filtered = useMemo(() => members.filter((member) => `${member.name} ${member.email}`.toLowerCase().includes(search.toLowerCase())), [members, search]);
  const invite = () => {
    const name = inviteEmail.split("@")[0].replace(/[._-]/g, " ");
    setMembers((current) => [...current, { name: name.replace(/\b\w/g, (letter) => letter.toUpperCase()), email: inviteEmail, initials: name.slice(0, 2).toUpperCase(), role: inviteRole, status: "Pending" }]);
    setInviteOpen(false); setInviteEmail(""); onToast("Invitation added to the pending list");
  };
  const confirm = () => {
    if (confirmAction?.type === "remove" && confirmAction.member) {
      setMembers((current) => current.filter((member) => member.email !== confirmAction.member?.email));
      onToast("Member removed from local workspace state");
    } else if (confirmAction?.type === "sessions") {
      setConfirmAction(null); onSessionExpired(); return;
    } else onToast("Leaving the only organization is unavailable");
    setConfirmAction(null);
  };
  return <main className="module-main settings-main">
    <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Workspace administration</div><h1>Settings</h1><p>Manage organization, account, members, and local sessions.</p></div><Badge tone="purple"><ShieldCheck size={13} /> Administrator</Badge></div>
    <div className="settings-layout">
      <nav className="settings-nav" aria-label="Settings sections">{(["Organization", "Account", "Members", "Sessions"] as Section[]).map((item) => { const Icon = item === "Organization" ? Building2 : item === "Account" ? UserRound : item === "Members" ? Users : Laptop; return <button key={item} className={section === item ? "active" : ""} onClick={() => setSection(item)}><Icon size={15} />{item}</button>; })}</nav>
      <div className="settings-content">
        {section === "Organization" && <>
          <SettingsHeading title="Organization details" copy="Basic workspace identity and regional preferences." />
          <section className="settings-card"><div className="settings-card-body form-stack"><label className="field"><span>Organization name</span><input defaultValue={appConfig.organization.name} /></label><label className="field"><span>Workspace identifier</span><input value="harbor-and-co" disabled /><small>Workspace identifiers cannot be changed in this prototype.</small></label><div className="field-row"><label className="field"><span>Time zone</span><select defaultValue="Eastern Time"><option>Eastern Time</option><option>Pacific Time</option><option>London</option></select></label><label className="field"><span>Date format</span><select><option>Month / Day / Year</option><option>Day / Month / Year</option></select></label></div></div><div className="settings-card-footer"><Button variant="primary" onClick={() => onToast("Organization preferences saved locally")}><Check size={14} /> Save changes</Button></div></section>
          <section className="settings-card danger-zone"><div><strong>Leave organization</strong><p>Administrators cannot leave the only locally available organization.</p></div><Button variant="danger" onClick={() => setConfirmAction({ type: "leave" })}>Leave organization</Button></section>
        </>}
        {section === "Account" && <>
          <SettingsHeading title="Profile and appearance" copy="Update your local profile and interface preferences." />
          <section className="settings-card"><div className="settings-card-body"><div className="profile-edit"><Avatar initials={appConfig.user.initials} tone="blue" /><div><strong>{appConfig.user.name}</strong><small>Profile image upload is unavailable</small></div><Button disabled>Upload image</Button></div><div className="field-row"><label className="field"><span>Full name</span><input defaultValue={appConfig.user.name} /></label><label className="field"><span>Email</span><input value={appConfig.user.email} disabled /></label></div></div><div className="settings-card-footer"><Button variant="primary" onClick={() => onToast("Profile changes saved locally")}>Save profile</Button></div></section>
          <section className="settings-card"><div className="settings-card-title"><Palette size={17} /><div><strong>Appearance</strong><p>Theme preference follows the control in the workspace header.</p></div></div><div className="appearance-options"><button className="active"><Monitor size={17} /> Current theme</button><button disabled><Palette size={17} /> Custom theme <Badge>Unavailable</Badge></button></div></section>
        </>}
        {section === "Members" && <>
          <div className="settings-heading-row"><SettingsHeading title="Members and invitations" copy="Admins can invite members and adjust supported roles." /><Button variant="primary" onClick={() => setInviteOpen(true)}><Plus size={15} /> Invite member</Button></div>
          <div className="member-tools"><label className="module-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search members" /></label><Badge>{members.filter((member) => member.status === "Pending").length} pending</Badge></div>
          <section className="settings-card member-list">{filtered.length ? filtered.map((member) => <div className="member-row" key={member.email}><Avatar initials={member.initials} tone={member.status === "Pending" ? "amber" : "blue"} /><span><strong>{member.name}{member.self ? " (you)" : ""}</strong><small>{member.email}</small></span><Badge tone={member.status === "Pending" ? "amber" : "green"}>{member.status}</Badge><select aria-label={`Role for ${member.name}`} value={member.role} disabled={member.self} onChange={(event) => setMembers((current) => current.map((item) => item.email === member.email ? { ...item, role: event.target.value as "Admin" | "Staff" } : item))}><option>Admin</option><option>Staff</option></select>{member.self ? <Button size="icon" variant="ghost" disabled aria-label="Current member cannot be removed"><LockKeyhole size={15} /></Button> : member.status === "Pending" ? <Button size="sm" onClick={() => onToast("Invitation reminder unavailable without email delivery")}>Resend</Button> : <Button size="icon" variant="ghost" aria-label={`Remove ${member.name}`} onClick={() => setConfirmAction({ type: "remove", member })}><Trash2 size={15} /></Button>}</div>) : <div className="module-empty compact"><Users size={22} /><strong>No members found</strong><p>Clear the search to see organization members.</p></div>}</section>
        </>}
        {section === "Sessions" && <>
          <SettingsHeading title="Session controls" copy="These controls affect local prototype state only." />
          <section className="settings-card"><div className="session-row"><span className="session-icon"><Laptop size={17} /></span><span><strong>Current browser</strong><small>Active now · Local prototype session</small></span><Badge tone="green">Current</Badge></div><div className="session-row restricted"><span className="session-icon"><LockKeyhole size={17} /></span><span><strong>Server sessions unavailable</strong><small>No authentication backend is connected, so other devices cannot be listed.</small></span><Badge>Unavailable</Badge></div><div className="settings-card-footer"><Button variant="danger" onClick={() => setConfirmAction({ type: "sessions" })}>End local session</Button></div></section>
        </>}
      </div>
    </div>
    <Modal open={inviteOpen} title="Invite member" description="Add a pending local invitation. Email delivery is unavailable." onClose={() => setInviteOpen(false)}><div className="dialog-body"><label className="field"><span>Email address</span><input autoFocus type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} placeholder="name@organization.example" /></label><label className="field"><span>Role</span><select value={inviteRole} onChange={(event) => setInviteRole(event.target.value as "Admin" | "Staff")}><option>Staff</option><option>Admin</option></select></label><div className="permission-state"><Mail size={16} /><span><strong>Delivery unavailable</strong><small>The invitation will only appear as a pending local record.</small></span></div></div><div className="dialog-footer"><Button onClick={() => setInviteOpen(false)}>Cancel</Button><Button variant="primary" disabled={!inviteEmail.includes("@")} onClick={invite}>Create invitation</Button></div></Modal>
    <Modal open={!!confirmAction} title={confirmAction?.type === "remove" ? "Remove member?" : confirmAction?.type === "sessions" ? "End local session?" : "Leave organization?"} description="Review this sensitive operation before continuing." onClose={() => setConfirmAction(null)}><div className="dialog-body"><div className="review-callout"><AlertCircle size={17} /><span><strong>This action requires confirmation</strong><p>{confirmAction?.type === "remove" ? `${confirmAction.member?.name} will lose access in local prototype state.` : confirmAction?.type === "sessions" ? "You will return to the sign-in screen with a session-expired message." : "This action is restricted because no other organization is available."}</p></span></div></div><div className="dialog-footer"><Button onClick={() => setConfirmAction(null)}>Cancel</Button><Button variant="danger" disabled={confirmAction?.type === "leave"} onClick={confirm}>{confirmAction?.type === "remove" ? "Remove member" : confirmAction?.type === "sessions" ? "End session" : "Unavailable"}</Button></div></Modal>
  </main>;
}

function SettingsHeading({ title, copy }: { title: string; copy: string }) { return <div className="settings-heading"><h2>{title}</h2><p>{copy}</p></div>; }
