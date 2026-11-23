/** Browser calls the host that served the page. The staging image uses this value. */
export const SAME_ORIGIN_API = "same-origin";

const LOCAL_API = "http://127.0.0.1:8000";

/**
 * Resolve the base URL prepended to `/api/v1/...`.
 *
 * Local development leaves the variable unset or points it at the API port.
 * A staging image sets `same-origin` so the bundle has no hostname. The browser
 * then calls `/api/v1` on whatever HTTPS origin Caddy served, and a new
 * hostname does not require a rebuild.
 */
export function resolveApiBaseUrl(configured: string | undefined): string {
  const value = configured?.trim() ?? "";
  if (value === SAME_ORIGIN_API) {
    return "";
  }
  if (value === "") {
    return LOCAL_API;
  }
  return value.replace(/\/$/, "");
}
