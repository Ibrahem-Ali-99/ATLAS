import { ApiError } from "@/lib/api";

export function RequestError({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Request failed";
  return (
    <p
      className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm leading-5 text-red-100"
      role="alert"
    >
      {message}
    </p>
  );
}
