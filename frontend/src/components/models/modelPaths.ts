import type { AuthRole } from "../../types/auth";

export function modelSettingsPath(role: AuthRole | undefined): string {
	return role === "admin" ? "/admin/models" : "/settings/models";
}
