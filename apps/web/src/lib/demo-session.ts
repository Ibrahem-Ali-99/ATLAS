import type { AuthSession } from "@/lib/types";

export const VISITOR_PREFIX = "harbor-visitor-";

export function isDemoSession(session: AuthSession | undefined): boolean {
  if (!session) {
    return false;
  }
  if (session.demo) {
    return true;
  }
  return session.memberships.some((item) => item.organization_slug.startsWith(VISITOR_PREFIX));
}
