export type ProposalPayload = Record<string, unknown>;

export function actionLabel(actionType: string): string {
  if (actionType === "create_lead") return "Create lead";
  if (actionType === "update_lead") return "Update lead";
  if (actionType === "prepare_customer_response") return "Prepare customer response";
  if (actionType === "request_appointment") return "Request appointment";
  return actionType.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

export function proposalTarget(payload: ProposalPayload): string {
  const company = stringValue(payload.company_name) ?? stringValue(payload.company);
  const contact = stringValue(payload.contact_name) ?? stringValue(payload.contact);
  const lead = stringValue(payload.title);
  if (company && contact) return `${contact} at ${company}`;
  if (company) return company;
  if (contact) return contact;
  if (lead) return lead;
  if (payload.attach_to === "run_lead") return "the lead created by this run";
  return "the selected CRM record";
}

export function proposalChange(actionType: string, payload: ProposalPayload): string {
  const status = stringValue(payload.status);
  const notes = stringValue(payload.notes);
  if (actionType === "update_lead" && status) {
    return `Set lead status to ${status.replaceAll("_", " ")}${notes ? ` and update its notes to “${notes}”` : ""}.`;
  }
  if (actionType === "create_lead") return `Create a new lead${status ? ` with status ${status.replaceAll("_", " ")}` : ""}.`;
  if (actionType === "prepare_customer_response") return "Prepare the proposed customer response for review.";
  if (actionType === "request_appointment") return "Prepare the proposed appointment for review.";
  return "Apply the stored proposal to the selected record.";
}

export function proposalRisk(actionType: string): string {
  if (actionType === "prepare_customer_response") return "External communication happens only after approval and execution.";
  if (actionType === "request_appointment") return "The configured calendar mode is used only after approval and execution.";
  return "Approval records the decision; execution is the step that changes CRM data.";
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
