import { ApiError } from "@/lib/api";

export function RequestError({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Request failed";
  return (
    <p className="text-sm text-red-300" role="alert">
      {message}
    </p>
  );
}
