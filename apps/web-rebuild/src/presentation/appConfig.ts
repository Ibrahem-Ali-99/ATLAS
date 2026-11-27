export const appConfig = {
  productName: "ATLAS",
  organization: { name: "Workspace", initials: "AT", descriptor: "Primary organization", slug: "" },
  user: { name: "", firstName: "", initials: "", email: "" },
};

export const workspace = {
  organizationId: "",
};

function initials(name: string): string {
  const letters = name
    .split(/\s+/)
    .filter((part) => /[A-Za-z0-9]/.test(part))
    .map((part) => part.replace(/[^A-Za-z0-9]/g, "")[0])
    .filter(Boolean)
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return letters || "AT";
}

export function bindWorkspace(input: {
  organizationId: string;
  organizationName: string;
  userName: string;
  email: string;
  slug?: string;
}): void {
  workspace.organizationId = input.organizationId;
  appConfig.organization.name = input.organizationName;
  appConfig.organization.slug = input.slug || "";
  appConfig.organization.initials = initials(input.organizationName);
  appConfig.user.name = input.userName;
  appConfig.user.firstName = input.userName.split(" ")[0] || input.userName;
  appConfig.user.initials = initials(input.userName);
  appConfig.user.email = input.email;
}
