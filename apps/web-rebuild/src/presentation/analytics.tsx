import { useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BarChart3,
  Building2,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Filter,
  Inbox,
  LoaderCircle,
  MessageSquareText,
  RotateCcw,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import { exportAnalytics, failureMessage, loadAnalytics, loadTeam, type AnalyticsSnapshot } from "@/data/resources";
import { initials } from "@/data/overview";
import { Avatar, Badge, Button, type Tone } from "./components";

type Metric = { label: string; value: string; detail: string; icon: typeof Building2; tone: Tone };
const tones: Tone[] = ["blue", "purple", "amber", "green", "red"];

export function AnalyticsWorkspace({ onToast, onOpenCrm }: { onToast: (message: string) => void; onOpenCrm?: () => void }) {
  const [range, setRange] = useState("Last 30 days");
  const [channel, setChannel] = useState("All channels");
  const [owner, setOwner] = useState("All owners");
  const [owners, setOwners] = useState<{ user_id: string; full_name: string }[]>([]);
  const [exporting, setExporting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [snapshot, setSnapshot] = useState<AnalyticsSnapshot | null>(null);
  const [drilldown, setDrilldown] = useState<Metric | null>(null);
  const period = range === "Last 7 days" ? "7d" : range === "Last 90 days" ? "90d" : "30d";
  const channelKey = channel === "Website chat" ? "webchat" : channel === "Email" ? "email" : channel === "WhatsApp" ? "whatsapp" : "all";
  const ownerId = owners.find((person) => person.full_name === owner)?.user_id || "";
  useEffect(() => {
    loadTeam().then((team) => setOwners(team.map((member) => ({ user_id: member.user_id, full_name: member.full_name })))).catch(() => setOwners([]));
  }, []);
  useEffect(() => {
    setLoading(true);
    loadAnalytics(period, channelKey, ownerId).then(setSnapshot).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setLoading(false));
  }, [period, channelKey, ownerId, onToast]);
  const metrics: Metric[] = snapshot ? [
    { label: "Companies", value: String(snapshot.companies_total), detail: "Company records", icon: Building2, tone: "blue" },
    { label: "Active leads", value: String(snapshot.leads_total), detail: "Leads in this range", icon: Users, tone: "purple" },
    { label: "Open inquiries", value: String(snapshot.open_inquiries), detail: `${snapshot.inquiries_total} inquiries`, icon: MessageSquareText, tone: "amber" },
    { label: "Open opportunities", value: String(snapshot.sales?.opportunities_total ?? 0), detail: "Opportunities", icon: Target, tone: "green" },
  ] : [];
  const activity = (snapshot?.customer_activity || []).slice(-12);
  const trend = activity.length ? activity.map((item) => item.inquiries + item.interactions) : [0];
  const maxTrend = Math.max(1, ...trend);
  const axisLabels = activity.length >= 3 ? [activity[0].day, activity[Math.floor((activity.length - 1) / 2)].day, activity[activity.length - 1].day] : ["Start", "Middle", "Latest"];
  const exportReport = () => {
    setExporting(true);
    void exportAnalytics(period, channelKey, "opportunities", ownerId).then(() => onToast("Opportunity report downloaded")).catch((error: unknown) => onToast(failureMessage(error))).finally(() => setExporting(false));
  };
  const pipeline = (snapshot?.lead_status || []).map((item, index) => ({ stage: item.status, count: item.count, tone: tones[index % tones.length] }));
  const largest = Math.max(1, ...pipeline.map((item) => item.count));
  const hasData = Boolean(snapshot);
  const applyFilter = (setter: (value: string) => void, value: string) => setter(value);
  const reset = () => {
    setRange("Last 30 days");
    setChannel("All channels");
    setOwner("All owners");
    onToast("Analytics filters reset");
  };
  return (
    <main className="module-main analytics-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Business activity</div><h1>Analytics</h1><p>Review customer activity, pipeline movement, and operational outcomes.</p></div><Button size="sm" disabled={exporting} onClick={exportReport}><CalendarDays size={13} /> {exporting ? "Exporting…" : "Export opportunities"}</Button></div>
      <section className="analytics-filters panel" aria-label="Analytics filters">
        <label><span>Date range</span><select value={range} onChange={(event) => applyFilter(setRange, event.target.value)}><option>Last 7 days</option><option>Last 30 days</option><option>Last 90 days</option></select></label>
        <label><span>Channel</span><select value={channel} onChange={(event) => applyFilter(setChannel, event.target.value)}><option>All channels</option><option>Website chat</option><option>Email</option><option>WhatsApp</option></select></label>
        <label><span>Owner</span><select value={owner} onChange={(event) => applyFilter(setOwner, event.target.value)}><option>All owners</option>{owners.map((person) => <option key={person.user_id}>{person.full_name}</option>)}</select></label>
        <Button onClick={reset}><RotateCcw size={14} /> Reset</Button>
      </section>
      {loading ? <div className="analytics-loading panel" role="status"><LoaderCircle size={20} /><span>Updating analytics…</span></div> : !hasData ? <div className="module-empty panel analytics-empty"><BarChart3 size={26} /><strong>No activity for this view</strong><p>No analytics were returned for {channel.toLowerCase()}.</p><Button size="sm" onClick={() => setChannel("All channels")}>Show all channels</Button></div> : <>
        <section className="analytics-metrics" aria-label="Business metrics">{metrics.map((metric) => { const Icon = metric.icon; return <button key={metric.label} className="analytics-metric panel" onClick={() => setDrilldown(metric)}><span className={`metric-icon badge-${metric.tone}`}><Icon size={16} /></span><span><small>{metric.label}</small><strong>{metric.value}</strong><p>{metric.detail}</p></span><ChevronRight size={15} /></button>; })}</section>
        <div className="analytics-grid">
          <section className="panel analytics-trend">
            <div className="panel-header"><div><h2>Customer activity trend</h2><p>Inquiries and interactions across the selected range</p></div><Badge tone="blue">{range}</Badge></div>
            <div className="chart-wrap">
              <svg viewBox="0 0 600 220" role="img" aria-labelledby="activity-chart-title activity-chart-desc">
                <title id="activity-chart-title">Customer activity trend</title><desc id="activity-chart-desc">{`Activity starts at ${trend[0]} and ends at ${trend[trend.length - 1]}. The tallest point is ${maxTrend}.`}</desc>
                <g className="chart-grid">{[30, 75, 120, 165, 210].map((y) => <line key={y} x1="48" x2="585" y1={y} y2={y} />)}</g>
                <g className="chart-y-axis" aria-hidden="true">{[[30, maxTrend], [75, Math.round(maxTrend * 0.75)], [120, Math.round(maxTrend * 0.5)], [165, Math.round(maxTrend * 0.25)], [210, 0]].map(([y, value]) => <text key={y} x="39" y={y + 3} textAnchor="end">{value}</text>)}</g>
                <polyline className="chart-line" points={trend.map((value, index) => `${52 + index * (500 / Math.max(trend.length, 1))},${210 - (value / maxTrend) * 160}`).join(" ")} />
                {trend.map((value, index) => <g className="chart-point-wrap" key={index} tabIndex={0} role="img" aria-label={`Period ${index + 1}: ${value} customer activities`}><circle className="chart-point" cx={52 + index * (500 / Math.max(trend.length, 1))} cy={210 - (value / maxTrend) * 160} r="4" /><g className="chart-tooltip" transform={`translate(${Math.min(520, Math.max(10, 52 + index * (500 / Math.max(trend.length, 1)) - 34))} ${Math.max(6, 210 - (value / maxTrend) * 160 - 35)})`}><rect width="72" height="25" rx="5" /><text x="36" y="16" textAnchor="middle">{value} activities</text></g></g>)}
              </svg>
              <div className="chart-axis">{axisLabels.map((label) => <span key={label}>{label}</span>)}</div>
            </div>
          </section>
          <section className="panel pipeline-distribution">
            <div className="panel-header"><div><h2>Pipeline distribution</h2><p>{snapshot?.leads_total ?? 0} leads by current stage</p></div></div>
            <div className="distribution-list">{pipeline.map((item) => <button key={item.stage}><span className={`status-dot dot-${item.tone}`} /><span>{item.stage}</span><i><b className={`fill-${item.tone}`} style={{ width: `${(item.count / largest) * 100}%` }} /></i><strong>{item.count}</strong><ChevronRight size={14} /></button>)}</div>
          </section>
          <section className="panel status-breakdown">
            <div className="panel-header"><div><h2>Inquiry status</h2><p>Current inquiry resolution status</p></div></div>
            <div className="breakdown-content"><div className="donut-chart" role="img" aria-label={`${snapshot?.open_inquiries ?? 0} open inquiries`}><span>{snapshot?.inquiries_total ?? 0}<small>Total</small></span></div><ul><li><span className="dot-blue" />Open<strong>{snapshot?.open_inquiries ?? 0}</strong></li><li><span className="dot-green" />Recorded<strong>{snapshot?.inquiries_total ?? 0}</strong></li></ul></div>
          </section>
          <section className="panel scoring-summary">
            <div className="panel-header"><div><h2>Lead scoring summary</h2><p>Current model outputs and availability</p></div><CircleHelp size={16} /></div>
            <div className="score-summary-list">{(snapshot?.recent_interactions || []).slice(0, 3).map((item) => <div key={item.id}><Avatar initials={initials(item.summary)} tone="blue" /><span><strong>{item.summary}</strong><small>{item.kind}</small></span><Badge>{item.created_at.slice(0, 10)}</Badge></div>)}</div>
          </section>
        </div>
      </>}
      {drilldown && <><button className="drawer-backdrop" aria-label="Close metric details" onClick={() => setDrilldown(null)} /><aside className="drawer analytics-drawer" aria-label={`${drilldown.label} details`}><div className="drawer-header"><div><h2>{drilldown.label}</h2><p>{range} · {channel} · {owner}</p></div><Button size="icon" variant="ghost" aria-label="Close metric details" onClick={() => setDrilldown(null)}><X size={17} /></Button></div><div className="drawer-content"><div className="metric-drilldown-total"><small>{drilldown.detail}</small><strong>{drilldown.value}</strong></div><section className="drawer-section"><h3>Linked CRM records</h3><div className="related-list">{(snapshot?.recent_interactions || []).slice(0, 5).map((item) => <div className="drilldown-item" key={item.id}><Building2 size={14} /><span><strong>{item.summary}</strong><small>{item.kind}</small></span></div>)}</div></section><div className="permission-state"><CircleHelp size={17} /><span><strong>Read-only analytics</strong><small>Changes must be made from the linked CRM record.</small></span></div></div><div className="drawer-footer"><Button onClick={() => setDrilldown(null)}>Close</Button>{onOpenCrm ? <Button variant="primary" onClick={onOpenCrm}>View in CRM <ArrowRight size={14} /></Button> : null}</div></aside></>}
    </main>
  );
}
