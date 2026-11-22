export const DATA_SCOPES = [
  { id: "operational", label: "Operational" },
  { id: "demo", label: "Demo" },
  { id: "evaluation", label: "Evaluation" },
  { id: "unknown", label: "Legacy" },
  { id: "all", label: "All records" },
] as const;

export type DataScope = (typeof DATA_SCOPES)[number]["id"];
