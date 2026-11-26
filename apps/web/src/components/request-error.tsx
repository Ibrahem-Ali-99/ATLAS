import { ApiError } from "@/lib/api";

export function RequestError({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Something went wrong. Try again.";
  return (
    <p
      className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm leading-5 text-foreground"
      role="alert"
    >
      {message}
    </p>
  );
}
