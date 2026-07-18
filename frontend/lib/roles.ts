export function normalizeRole(role: string): string {
  const normalized = role.trim().toLowerCase();
  if (normalized === "super_admin") return "admin";
  if (normalized === "reader") return "user";
  return normalized;
}

export function hasAdminRole(roles: string[] | undefined | null): boolean {
  return Boolean(roles?.some((role) => normalizeRole(role) === "admin"));
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
  return normalized.replace(/_/g, " ");
}
