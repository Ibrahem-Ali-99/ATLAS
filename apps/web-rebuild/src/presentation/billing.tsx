import { useEffect, useState } from "react";
import { AlertCircle, ArrowRight, Check, CircleGauge, CreditCard, ExternalLink, LockKeyhole, PackageCheck, Sparkles, X } from "lucide-react";
import { checkoutBilling, failureMessage, loadBilling, loadBillingPlans, openBillingPortal, type BillingSnapshot } from "@/data/resources";
import { Badge, Button } from "./components";

export function BillingWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const [unavailable, setUnavailable] = useState<"checkout" | "portal" | null>(null);
  const [billing, setBilling] = useState<BillingSnapshot | null>(null);
  const [plans, setPlans] = useState<{ code: string; name: string }[]>([]);
  const [notice, setNotice] = useState("");
  const [pendingPlan, setPendingPlan] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const refresh = () => loadBilling().then(setBilling).catch((error: unknown) => setNotice(failureMessage(error)));
  useEffect(() => {
    refresh();
    loadBillingPlans().then(setPlans).catch(() => setPlans([]));
  }, []);
  const sandbox = billing?.mode !== "stripe";
  const startCheckout = (planCode: string) => {
    if (billing?.mode === "stripe") {
      setNotice("Checkout would open a payment provider. This screen does not start a charge.");
      setUnavailable("checkout");
      return;
    }
    setPendingPlan(planCode);
  };
  const confirmCheckout = () => {
    if (!pendingPlan) return;
    setWorking(true);
    void checkoutBilling(pendingPlan).then((result) => {
      setNotice(result.mode === "sandbox" ? `Sandbox plan recorded as ${result.status}.` : "The provider returned a checkout session. This screen does not open it.");
      setPendingPlan(null);
      setUnavailable(null);
      return refresh();
    }).catch((error: unknown) => setNotice(failureMessage(error))).finally(() => setWorking(false));
  };
  const openPortal = () => {
    if (billing?.mode === "stripe") {
      setNotice("The billing portal would open a payment provider. This screen does not open it.");
      setUnavailable("portal");
      return;
    }
    setWorking(true);
    void openBillingPortal().then(() => setNotice("The billing provider returned a portal session.")).catch((error: unknown) => { setNotice(failureMessage(error)); setUnavailable("portal"); }).finally(() => setWorking(false));
  };
  return <main className="module-main billing-main">
    <div className="module-heading"><div><div className="eyebrow"><span className="live-dot" /> Subscription management</div><h1>Billing</h1><p>Review the stored plan, usage, and whether a payment provider can be opened.</p></div><Badge tone={sandbox ? "amber" : "green"}><AlertCircle size={13} /> {billing?.mode || "Loading"}</Badge></div>
    <div className="billing-alert"><AlertCircle size={18} /><span><strong>{billing?.checkout_available ? "Checkout can be opened" : "Checkout cannot start a payment"}</strong><p>{notice || (billing ? `Plan ${billing.subscription.plan_code} is ${billing.subscription.status}. Billing mode is ${billing.mode}.` : "Loading billing status.")}</p></span></div>
    <section className="billing-grid">
      <article className="settings-card current-plan"><div className="plan-heading"><span className="integration-icon badge-purple"><Sparkles size={18} /></span><span><small>Current plan</small><strong>{billing?.subscription.plan_code || "Unknown"}</strong></span><Badge tone={sandbox ? "amber" : "green"}>{billing?.subscription.status || "Unknown"}</Badge></div><p>{billing?.checkout_available ? "A sandbox plan change is recorded by the API. A card payment is not started from this screen." : "Checkout is unavailable, so no card is charged from this screen."}</p><div className="plan-actions"><Button variant="primary" disabled={!billing?.checkout_available} onClick={() => billing && startCheckout(billing.subscription.plan_code)}>Manage plan <ArrowRight size={14} /></Button><Button disabled={working} onClick={openPortal}>Billing portal <ExternalLink size={14} /></Button></div></article>
      <article className="settings-card payment-state"><CreditCard size={20} /><div><strong>{billing?.checkout_available ? "Checkout can be opened" : "Checkout is unavailable"}</strong><p>{billing?.portal_available ? "The billing portal can be opened." : "The billing portal is not available."} No payment is recorded from this screen.</p></div><Badge tone={billing?.checkout_available ? "blue" : "red"}>{billing?.checkout_available ? "Available" : "Unavailable"}</Badge></article>
    </section>
    <div className="billing-sections">
      <section className="settings-card"><div className="settings-card-title"><CircleGauge size={17} /><div><strong>Usage availability</strong><p>Usage recorded for the current plan.</p></div></div><div className="usage-list">{Object.entries(billing?.usage || {}).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{value}</strong></div>)}</div></section>
      <section className="settings-card"><div className="settings-card-title"><PackageCheck size={17} /><div><strong>Entitlements</strong><p>What this workspace can do with the current plan.</p></div></div><ul className="entitlement-list"><li><Check size={15} /> CRM, inbox, knowledge, and assistant <Badge tone="green">Available</Badge></li><li><Check size={15} /> Workflows and approvals <Badge tone="blue">Recorded</Badge></li><li><LockKeyhole size={15} /> Live customer messaging <Badge>Disabled</Badge></li><li><LockKeyhole size={15} /> Card checkout <Badge>{billing?.checkout_available ? "Available" : "Unavailable"}</Badge></li></ul></section>
    </div>
    <section className="available-plans"><div className="settings-heading"><h2>Available plans</h2><p>Plans returned by the billing catalog. A disabled plan cannot start a payment.</p></div><div className="plan-grid">{plans.map((plan) => <article className="settings-card" key={plan.code}><Badge tone={plan.code === billing?.subscription.plan_code ? "blue" : "neutral"}>{plan.code === billing?.subscription.plan_code ? "Current" : plan.code}</Badge><h3>{plan.name}</h3><p>Stored catalog entry.</p><Button disabled={!billing?.checkout_available || plan.code === billing?.subscription.plan_code} onClick={() => startCheckout(plan.code)}>{plan.code === billing?.subscription.plan_code ? "Current" : billing?.mode === "stripe" ? "Review checkout" : "Update sandbox plan"}</Button></article>)}</div></section>
    {(unavailable || pendingPlan) && <><button className="drawer-backdrop" aria-label="Close billing" onClick={() => { setUnavailable(null); setPendingPlan(null); }} /><aside className="drawer billing-drawer" aria-label="Billing action"><div className="drawer-header"><div><h2>{pendingPlan ? `Update ${pendingPlan}` : unavailable === "checkout" ? "Checkout unavailable" : "Billing portal unavailable"}</h2><p>{notice || "No payment is started from this screen."}</p></div><Button size="icon" variant="ghost" aria-label="Close billing" onClick={() => { setUnavailable(null); setPendingPlan(null); }}><X size={17} /></Button></div><div className="drawer-content"><div className="module-empty"><CreditCard size={25} /><strong>{pendingPlan ? "Confirm the sandbox plan change" : `Unable to open ${unavailable}`}</strong><p>{pendingPlan ? "This records the selected plan in the workspace. It does not charge a card." : notice || "The billing provider did not accept this request."}</p><div className="plan-actions">{pendingPlan && <Button variant="primary" disabled={working} onClick={confirmCheckout}>{working ? "Saving…" : "Record plan"}</Button>}<Button onClick={() => { setUnavailable(null); setPendingPlan(null); }}>Return to billing</Button></div></div></div></aside></>}
  </main>;
}
