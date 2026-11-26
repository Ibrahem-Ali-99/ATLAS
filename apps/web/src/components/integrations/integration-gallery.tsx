import { Badge } from "@/components/ui/badge";
import { CalendarDays, CreditCard, Globe2, Mail, MessageCircle, Search, Send, Sparkles, Workflow } from "lucide-react";

const gallery = [
  { name: "Email", purpose: "Deliver approved replies and campaign messages.", note: "This demonstration keeps messages inside the session.", status: "Simulated", color: "#1a73e8", icon: Mail },
  { name: "Website chat", purpose: "Bring website conversations into Inbox.", note: "Sample website messages are included.", status: "Included", color: "#2856d7", icon: Globe2 },
  { name: "WhatsApp", purpose: "Receive WhatsApp messages and send approved replies.", note: "Not connected to WhatsApp in this demonstration.", status: "Not connected", color: "#25D366", icon: MessageCircle },
  { name: "Google Calendar", purpose: "Place approved appointments on a calendar.", note: "Appointments stay in ATLAS during this demonstration.", status: "Simulated", color: "#4285F4", icon: CalendarDays },
  { name: "n8n", purpose: "Continue a lead in an external workflow.", note: "This demonstration does not call an external workflow.", status: "Not connected", color: "#EA4B71", icon: Workflow },
  { name: "Assistant", purpose: "Answer from the records in the workspace.", note: "Answers use the included records.", status: "Demonstration", color: "#10a37f", icon: Sparkles },
  { name: "Document search", purpose: "Find passages in uploaded company documents.", note: "Search stays inside this demonstration.", status: "Demonstration", color: "#5b4bdb", icon: Search },
  { name: "Stripe", purpose: "Manage the workspace subscription.", note: "This demonstration does not open a payment account.", status: "Not connected", color: "#635BFF", icon: CreditCard },
  { name: "Resend", purpose: "Send campaigns and record delivery feedback.", note: "Not connected in this demonstration.", status: "Not connected", color: "#111111", icon: Send },
] as const;

export function IntegrationGallery() {
  return (
    <section aria-label="Supported integrations">
      <div className="integration-toolbar">
        <p>Connection settings stay with a workspace administrator.</p>
        <div className="integration-legend">
          <Badge>Included</Badge>
          <Badge variant="secondary">Simulated</Badge>
          <Badge variant="secondary">Not connected</Badge>
        </div>
      </div>
      <div className="provider-board">
        {gallery.map((item) => {
          const Icon = item.icon;
          return (
            <article className="provider-tile" key={item.name}>
              <header>
                <span className="provider-mark" style={{ background: item.color }}><Icon size={18} aria-hidden /></span>
                <span>
                  <strong>{item.name}</strong>
                  <small>{item.purpose}</small>
                </span>
              </header>
              <Badge variant="secondary">{item.status}</Badge>
              <ul className="provider-caps"><li>{item.note}</li></ul>
            </article>
          );
        })}
      </div>
    </section>
  );
}
