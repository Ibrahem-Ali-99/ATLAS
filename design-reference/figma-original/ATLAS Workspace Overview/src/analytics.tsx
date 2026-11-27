import { useState } from "react";
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
import { Avatar, Badge, Button, type Tone } from "./components";

type Metric = { label: string; value: string; detail: string; icon: typeof Building2; tone: Tone };
const metrics: Metric[] = [
  { label: "Companies", value: "4", detail: "Active company records", icon: Building2, tone: "blue" },
  { label: "Active leads", value: "13", detail: "15 total leads", icon: Users, tone: "purple" },
  { label: "Open inquiries", value: "16", detail: "Awaiting resolution", icon: MessageSquareText, tone: "amber" },
  { label: "Open opportunities", value: "4", detail: "Across active pipeline stages", icon: Target, tone: "green" },
];
const trend = [8, 11, 9, 13, 12, 16, 15, 18, 17, 20, 19, 22];
const pipeline = [
  { stage: "New", count: 7, tone: "blue" as Tone },
  { stage: "Contacted", count: 1, tone: "purple" as Tone },
  { stage: "Qualified", count: 5, tone: "amber" as Tone },
  { stage: "Won", count: 1, tone: "green" as Tone },
  { stage: "Lost", count: 1, tone: "red" as Tone },
];

export function AnalyticsWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [range, setRange] = useState("Last 30 days");
  const [channel, setChannel] = useState("All channels");
  const [owner, setOwner] = useState("All owners");
  const [loading, setLoading] = useState(false);
  const [drilldown, setDrilldown] = useState<Metric | null>(null);
  const hasData = channel !== "WhatsApp";
  const applyFilter = (setter: (value: string) => void, value: string) => {
    setter(value);
    setLoading(true);
    window.setTimeout(() => setLoading(false), 450);
  };
  const reset = () => {
    setRange("Last 30 days");
    setChannel("All channels");
    setOwner("All owners");
    onToast("Analytics filters reset");
  };
  return (
    <main className="module-main analytics-main">
      <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Business activity</div><h1>Analytics</h1><p>Review customer activity, pipeline movement, and operational outcomes.</p></div><Badge tone="neutral"><CalendarDays size={13} /> Updated 4 min ago</Badge></div>
      <section className="analytics-filters panel" aria-label="Analytics filters">
        <label><span>Date range</span><select value={range} onChange={(event) => applyFilter(setRange, event.target.value)}><option>Last 7 days</option><option>Last 30 days</option><option>Last 90 days</option></select></label>
        <label><span>Channel</span><select value={channel} onChange={(event) => applyFilter(setChannel, event.target.value)}><option>All channels</option><option>Website chat</option><option>Email</option><option>WhatsApp</option></select></label>
        <label><span>Owner</span><select value={owner} onChange={(event) => applyFilter(setOwner, event.target.value)}><option>All owners</option><option>Olivia Martin</option><option>Sam Rivera</option><option>Maya Chen</option></select></label>
        <Button onClick={reset}><RotateCcw size={14} /> Reset</Button>
      </section>
      {loading ? <div className="analytics-loading panel" role="status"><LoaderCircle size={20} /><span>Updating analytics…</span></div> : !hasData ? <div className="module-empty panel analytics-empty"><BarChart3 size={26} /><strong>No activity for this channel</strong><p>No WhatsApp activity is present in the current prototype records.</p><Button size="sm" onClick={() => setChannel("All channels")}>Show all channels</Button></div> : <>
        <section className="analytics-metrics" aria-label="Business metrics">{metrics.map((metric) => { const Icon = metric.icon; return <button key={metric.label} className="analytics-metric panel" onClick={() => setDrilldown(metric)}><span className={`metric-icon badge-${metric.tone}`}><Icon size={16} /></span><span><small>{metric.label}</small><strong>{metric.value}</strong><p>{metric.detail}</p></span><ChevronRight size={15} /></button>; })}</section>
        <div className="analytics-grid">
          <section className="panel analytics-trend">
            <div className="panel-header"><div><h2>Customer activity trend</h2><p>Inquiries and interactions across the selected range</p></div><Badge tone="blue">{range}</Badge></div>
            <div className="chart-wrap">
              <svg viewBox="0 0 600 220" role="img" aria-labelledby="activity-chart-title activity-chart-desc">
                <title id="activity-chart-title">Customer activity trend</title><desc id="activity-chart-desc">Activity rises from 8 events at the start of the period to 22 events at the end, with several small declines.</desc>
                <g className="chart-grid">{[30, 75, 120, 165, 210].map((y) => <line key={y} x1="48" x2="585" y1={y} y2={y} />)}</g>
                <g className="chart-y-axis" aria-hidden="true">{[[30, 24], [75, 18], [120, 12], [165, 6], [210, 0]].map(([y, value]) => <text key={y} x="39" y={y + 3} textAnchor="end">{value}</text>)}</g>
                <polyline className="chart-line" points={trend.map((value, index) => `${52 + index * 48},${210 - value * 7.5}`).join(" ")} />
                {trend.map((value, index) => <g className="chart-point-wrap" key={index} tabIndex={0} role="img" aria-label={`Period ${index + 1}: ${value} customer activities`}><circle className="chart-point" cx={52 + index * 48} cy={210 - value * 7.5} r="4" /><g className="chart-tooltip" transform={`translate(${Math.min(520, Math.max(10, 52 + index * 48 - 34))} ${Math.max(6, 210 - value * 7.5 - 35)})`}><rect width="72" height="25" rx="5" /><text x="36" y="16" textAnchor="middle">{value} activities</text></g></g>)}
              </svg>
              <div className="chart-axis"><span>30 days ago</span><span>15 days ago</span><span>Today</span></div>
            </div>
          </section>
          <section className="panel pipeline-distribution">
            <div className="panel-header"><div><h2>Pipeline distribution</h2><p>15 leads by current stage</p></div></div>
            <div className="distribution-list">{pipeline.map((item) => <button key={item.stage} onClick={() => onToast(`Opening ${item.stage} leads in CRM`)}><span className={`status-dot dot-${item.tone}`} /><span>{item.stage}</span><i><b className={`fill-${item.tone}`} style={{ width: `${item.count / 7 * 100}%` }} /></i><strong>{item.count}</strong><ChevronRight size={14} /></button>)}</div>
          </section>
          <section className="panel status-breakdown">
            <div className="panel-header"><div><h2>Inquiry status</h2><p>Current inquiry resolution status</p></div></div>
            <div className="breakdown-content"><div className="donut-chart" role="img" aria-label="Inquiry status: 8 open, 5 in progress, 3 resolved"><span>16<small>Total</small></span></div><ul><li><span className="dot-blue" />Open<strong>8</strong></li><li><span className="dot-amber" />In progress<strong>5</strong></li><li><span className="dot-green" />Resolved<strong>3</strong></li></ul></div>
          </section>
          <section className="panel scoring-summary">
            <div className="panel-header"><div><h2>Lead scoring summary</h2><p>Current model outputs and availability</p></div><CircleHelp size={16} /></div>
            <div className="score-summary-list"><div><Avatar initials="MP" tone="green" /><span><strong>Mina Park</strong><small>Arcade · Qualified</small></span><Badge tone="green">Score 88</Badge></div><div><Avatar initials="TB" tone="amber" /><span><strong>Theo Brooks</strong><small>Layers · Contacted</small></span><Badge tone="amber">Score 72</Badge></div><div><Avatar initials="JB" tone="neutral" /><span><strong>Jon Bell</strong><small>Vertex · New</small></span><Badge>Unavailable</Badge></div></div>
            <div className="prediction-unavailable compact-prediction"><Sparkles size={17} /><strong>1 prediction unavailable</strong><p>More customer activity is required before a score can be produced.</p></div>
          </section>
        </div>
      </>}
      {drilldown && <><button className="drawer-backdrop" aria-label="Close metric details" onClick={() => setDrilldown(null)} /><aside className="drawer analytics-drawer" aria-label={`${drilldown.label} details`}><div className="drawer-header"><div><h2>{drilldown.label}</h2><p>{range} · {channel} · {owner}</p></div><Button size="icon" variant="ghost" aria-label="Close metric details" onClick={() => setDrilldown(null)}><X size={17} /></Button></div><div className="drawer-content"><div className="metric-drilldown-total"><small>{drilldown.detail}</small><strong>{drilldown.value}</strong></div><section className="drawer-section"><h3>Linked CRM records</h3><div className="related-list">{["Arcade", "Northstar", "Layers"].map((name, index) => <button key={name} onClick={() => onToast(`Opening ${name} in CRM`)}><Building2 size={14} /><span><strong>{name}</strong><small>{index === 0 ? "Updated today" : "Updated this week"}</small></span><ChevronRight size={14} /></button>)}</div></section><div className="permission-state"><CircleHelp size={17} /><span><strong>Read-only analytics</strong><small>Changes must be made from the linked CRM record.</small></span></div></div><div className="drawer-footer"><Button onClick={() => setDrilldown(null)}>Close</Button><Button variant="primary" onClick={() => onToast("Opening CRM filtered view")}>View in CRM <ArrowRight size={14} /></Button></div></aside></>}
    </main>
  );
}
