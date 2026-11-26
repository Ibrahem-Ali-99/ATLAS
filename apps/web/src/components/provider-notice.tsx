"use client";

import { useQuery } from "@tanstack/react-query";

import { RequestError } from "@/components/request-error";
import { apiFetch } from "@/lib/api";

export type ProviderStatus = {
  llm_provider: string;
  llm_model: string;
  llm_ready: boolean;
  llm_detail: string;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimensions: number;
  embedding_ready: boolean;
  embedding_detail: string;
  incompatible_documents: number;
};

export function getProviderStatus(organizationId: string): Promise<ProviderStatus> {
  return apiFetch(`/api/v1/organizations/${organizationId}/provider-status`);
}

export function ProviderNotice({
  organizationId,
  detail = false,
  compact = false,
}: {
  organizationId: string;
  detail?: boolean;
  compact?: boolean;
}) {
  const status = useQuery({
    queryKey: ["provider-status", organizationId],
    queryFn: () => getProviderStatus(organizationId),
    retry: false,
  });
  if (status.isPending) {
    return null;
  }
  if (status.isError) {
    return <RequestError error={status.error} />;
  }
  const data = status.data;
  if (compact) {
    if (!data.llm_ready) {
      return <p className="text-xs text-subtle">{data.llm_detail}</p>;
    }
    return <p className="text-xs font-medium text-success">Assistant connected</p>;
  }
  const problem = !data.llm_ready || !data.embedding_ready || data.incompatible_documents > 0;
  if (!detail && !problem) {
    return null;
  }
  return (
    <section className="rounded-[10px] bg-muted p-4 text-sm" aria-live="polite">
      <h2 className="font-medium">Connected services</h2>
      <p className="mt-1 text-muted-foreground">Secrets stay hidden.</p>
      <dl className="mt-3 space-y-2">
        <div>
          <dt className="text-muted-foreground">Assistant</dt>
          <dd>
            {data.llm_provider} · {data.llm_model}. {data.llm_detail}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Document search</dt>
          <dd>
            {data.embedding_provider} · {data.embedding_model} · {data.embedding_dimensions} values. {data.embedding_detail}
          </dd>
        </div>
      </dl>
      {data.incompatible_documents > 0 ? (
        <p className="mt-3 leading-6 text-muted-foreground">
          {data.incompatible_documents} ready {data.incompatible_documents === 1 ? "document was" : "documents were"} embedded with a different model. Reindex {data.incompatible_documents === 1 ? "it" : "them"} before vector search can use the current model. The file and its citations stay in place.
        </p>
      ) : null}
    </section>
  );
}
