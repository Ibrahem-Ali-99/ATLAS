import { apiFetch } from "@/lib/api";

export type EmbeddingReindex = {
  status: "building" | "completed" | "failed" | "cancelled";
  model: string;
  dimensions: number;
  total_chunks: number;
  staged_chunks: number;
  error_code: string | null;
};

const path = (id: string) => `/api/v1/organizations/${id}/knowledge/embedding-reindex`;
export const getEmbeddingReindex = (id: string) => apiFetch<EmbeddingReindex | null>(path(id));
export const startEmbeddingReindex = (id: string, target: {
  provider: string;
  base_url: string;
  model: string;
  dimensions: number;
  credentials?: string;
  expected_version?: number;
}) => apiFetch<EmbeddingReindex>(path(id), { method: "POST", body: JSON.stringify(target) });
export const cancelEmbeddingReindex = (id: string) => apiFetch<void>(path(id), { method: "DELETE" });
