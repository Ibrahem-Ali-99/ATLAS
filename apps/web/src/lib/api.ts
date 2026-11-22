import type { AuthSession, HealthStatus, ReadyStatus } from "@/lib/types";

export const sessionQueryKey = ["session"] as const;

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

let csrfToken: string | null = null;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
  };
};

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const method = (init.method ?? "GET").toUpperCase();
  if (csrfToken && method !== "GET" && method !== "HEAD") {
    headers.set("X-CSRF-Token", csrfToken);
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers,
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network_error", "The API is unreachable. Start the backend and try again.");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = (await response.json().catch(() => null)) as (T & ErrorEnvelope) | null;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "request_failed",
      payload?.error?.message ?? "Request failed",
    );
  }
  if (payload === null) {
    throw new ApiError(response.status, "invalid_response", "The API returned an unreadable response.");
  }
  return payload;
}

export async function getSession(): Promise<AuthSession> {
  const session = await apiFetch<AuthSession>("/api/v1/auth/me");
  setCsrfToken(session.csrf_token);
  return session;
}

export async function login(input: { email: string; password: string }): Promise<AuthSession> {
  const session = await apiFetch<AuthSession>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
  setCsrfToken(session.csrf_token);
  return session;
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
  setCsrfToken(null);
}

export function getHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/api/v1/health");
}

export function getReady(): Promise<ReadyStatus> {
  return apiFetch<ReadyStatus>("/api/v1/ready");
}

export const sessionQueryOptions = {
  queryKey: sessionQueryKey,
  queryFn: getSession,
  retry: false,
  staleTime: 60_000,
} as const;
