export type MembershipRole = "admin" | "staff";

export type User = {
  id: string;
  email: string;
  full_name: string;
};

export type Membership = {
  id: string;
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  role: MembershipRole;
};

export type AuthSession = {
  user: User;
  memberships: Membership[];
  csrf_token: string;
  demo?: boolean;
  demo_expires_at?: string | null;
};

export type OrganizationRecord = {
  id: string;
  name: string;
  slug: string;
  role: MembershipRole;
};

export type HealthStatus = {
  status: "ok";
  service: "atlas-api";
};

export type ReadyStatus = {
  status: "ok";
  database: "ok";
};
