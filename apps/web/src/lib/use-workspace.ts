"use client";

import { useQuery } from "@tanstack/react-query";

import { sessionQueryOptions } from "@/lib/api";

export function useWorkspace() {
  const session = useQuery(sessionQueryOptions);
  const membership = session.data?.memberships[0] ?? null;
  return {
    organizationId: membership?.organization_id ?? null,
    organizationName: membership?.organization_name ?? null,
    role: membership?.role ?? null,
    userId: session.data?.user.id ?? null,
  };
}
