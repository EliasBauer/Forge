import type { AuthUser } from "../contexts/AuthContext";

export const canEdit = (user: AuthUser | null): boolean =>
  user !== null &&
  (user.groups.includes("Admin") || user.groups.includes("Projektleiter"));

export const canViewFinancials = (user: AuthUser | null): boolean =>
  user !== null && !user.groups.includes("Monteur");

export const canManageStundensaetze = (user: AuthUser | null): boolean =>
  user !== null &&
  (user.groups.includes("Admin") || user.groups.includes("Projektleiter"));

export const canCreateProject = (user: AuthUser | null): boolean =>
  user !== null &&
  (user.groups.includes("Admin") || user.groups.includes("Projektleiter"));
