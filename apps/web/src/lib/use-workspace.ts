"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, createElement, useContext, useMemo, useState, type ReactNode } from "react";

import { sessionQueryOptions } from "@/lib/api";

const STORAGE_KEY = "atlas.selectedOrganization";
type WorkspaceSelection = { organizationId: string | null; setOrganizationId: (id: string) => void };
const WorkspaceContext = createContext<WorkspaceSelection | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const session = useQuery(sessionQueryOptions);
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    typeof window === "undefined" ? null : window.localStorage.getItem(STORAGE_KEY),
  );
  const memberships = useMemo(() => session.data?.memberships ?? [], [session.data?.memberships]);
  const activeId = useMemo(
    () => memberships.some((item) => item.organization_id === selectedId)
      ? selectedId
      : memberships[0]?.organization_id ?? null,
    [memberships, selectedId],
  );
  const setOrganizationId = (id: string) => {
    if (!memberships.some((item) => item.organization_id === id)) return;
    void queryClient.cancelQueries({ predicate: (query) => query.queryKey[0] !== "session" });
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
    window.localStorage.setItem(STORAGE_KEY, id);
    setSelectedId(id);
  };
  return createElement(WorkspaceContext.Provider, { value: { organizationId: activeId, setOrganizationId } }, children);
}

export function useWorkspace() {
  const session = useQuery(sessionQueryOptions);
  const selection = useContext(WorkspaceContext);
  const memberships = session.data?.memberships ?? [];
  const membership = memberships.find((item) => item.organization_id === selection?.organizationId) ?? memberships[0] ?? null;
  return {
    organizationId: membership?.organization_id ?? null,
    organizationName: membership?.organization_name ?? null,
    role: membership?.role ?? null,
    userId: session.data?.user.id ?? null,
    memberships,
    setOrganizationId: selection?.setOrganizationId ?? (() => undefined),
  };
}
