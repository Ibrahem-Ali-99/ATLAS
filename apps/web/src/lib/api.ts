import { resolveApiBaseUrl } from "@/lib/api-base";
import type { AuthSession, HealthStatus, ReadyStatus } from "@/lib/types";

export const sessionQueryKey = ["session"] as const;

const API_URL = resolveApiBaseUrl(process.env.NEXT_PUBLIC_API_URL);

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
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body !== undefined && !isForm && !headers.has("Content-Type")) {
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

  const unreadable = Symbol("unreadable response");
  const payload = await response.json().catch(() => unreadable) as
    (T & ErrorEnvelope) | null | typeof unreadable;
  if (!response.ok) {
    const error = payload === unreadable ? undefined : payload?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "request_failed",
      error?.message ?? "Request failed",
    );
  }
  if (payload === unreadable) {
    throw new ApiError(response.status, "invalid_response", "The API returned an unreadable response.");
  }
  return payload as T;
}

export async function apiText(path: string): Promise<{ text: string; filename: string | null }> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { credentials: "include", cache: "no-store" });
  } catch {
    throw new ApiError(0, "network_error", "The API is unreachable. Start the backend and try again.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as ErrorEnvelope | null;
    throw new ApiError(response.status, payload?.error?.code ?? "request_failed", payload?.error?.message ?? "Request failed");
  }
  const match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "");
  return { text: await response.text(), filename: match?.[1] ?? null };
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

export function requestPasswordReset(email: string): Promise<{ detail: string }> {
  return apiFetch("/api/v1/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
}

export function confirmPasswordReset(token: string, password: string): Promise<void> {
  return apiFetch("/api/v1/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) });
}

export function getHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/api/v1/health");
}

export function getReady(): Promise<ReadyStatus> {
  return apiFetch<ReadyStatus>("/api/v1/ready");
}

export async function apiStream<T>(
  path: string,
  body: unknown,
  onToken: (text: string) => void,
  onPhase?: (phase: string) => void,
  signal?: AbortSignal,
): Promise<T> {
  const headers = new Headers({
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  });
  if (csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      credentials: "include",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(0, "cancelled", "Stopped before the answer was saved.");
    }
    throw new ApiError(0, "network_error", "The API is unreachable. Start the backend and try again.");
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as ErrorEnvelope | null;
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "request_failed",
      payload?.error?.message ?? "Request failed",
    );
  }
  if (!response.body) {
    throw new ApiError(502, "invalid_response", "The assistant stream did not start.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: T | null = null;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const name = /^event: (.+)$/m.exec(frame)?.[1];
        const data = /^data: (.*)$/m.exec(frame)?.[1];
        if (!name || data === undefined) {
          continue;
        }
        if (name === "token") {
          const payload = JSON.parse(data) as { text?: unknown };
          if (typeof payload.text === "string") {
            onToken(payload.text);
          }
        } else if (name === "phase") {
          const payload = JSON.parse(data) as { phase?: unknown };
          if (typeof payload.phase === "string") {
            onPhase?.(payload.phase);
          }
        } else if (name === "done") {
          result = JSON.parse(data) as T;
        } else if (name === "error") {
          const payload = JSON.parse(data) as { code?: unknown; message?: unknown };
          throw new ApiError(
            502,
            typeof payload.code === "string" ? payload.code : "llm_failed",
            typeof payload.message === "string" ? payload.message : "The assistant failed.",
          );
        }
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      if (result) return result;
      throw new ApiError(0, "cancelled", "Stopped before the answer was saved.");
    }
    throw error;
  }
  if (result === null) {
    throw new ApiError(502, "invalid_response", "The assistant stream ended without a reply.");
  }
  return result;
}

export const sessionQueryOptions = {
  queryKey: sessionQueryKey,
  queryFn: getSession,
  retry: false,
  staleTime: 60_000,
} as const;
