export function normalizeRole(role: string): string {
  const normalized = role.trim().toLowerCase();
  if (normalized === "super_admin") return "admin";
  if (normalized === "reader") return "user";
  return normalized;
}

export function hasAdminRole(roles: string[] | undefined | null): boolean {
  return Boolean(roles?.some((role) => normalizeRole(role) === "admin"));
}

export function hasNamedRole(roles: string[] | undefined | null, requiredRole: string): boolean {
  const normalizedRequiredRole = normalizeRole(requiredRole);
  return Boolean(roles?.some((role) => normalizeRole(role) === normalizedRequiredRole));
}

export function hasDocumentOrganizationAdvancedAccess(roles: string[] | undefined | null): boolean {
  return hasAdminRole(roles) || hasNamedRole(roles, "editor");
}

export function hasProviderAccess(roles: string[] | undefined | null): boolean {
  return Boolean(
    roles?.some((role) => {
      const normalized = normalizeRole(role);
      return normalized === "admin" || normalized === "editor" || normalized === "user";
    }),
  );
}

export function getRoleLabel(role: string): string {
  const normalized = normalizeRole(role);
  if (normalized === "admin") return "Admin";
  if (normalized === "editor") return "Editor";
  if (normalized === "user") return "User";
  if (normalized === "service") return "System Service";
  if (normalized === "feedback_manager") return "Feedback Manager";
  if (normalized === "collection_moderator") return "Qel Connect Moderator";
  if (normalized === "support_manager") return "Support Manager";
  return normalized.replace(/_/g, " ");
}
