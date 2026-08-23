import { formatRoleChip, ROLE_CODES } from "../../lib/lifecycle";
import type { DataRole } from "../../types/design";

export function RoleBadge({ role }: { role: DataRole }) {
  return (
    <span className={`role-badge role-${role}`} title={ROLE_CODES[role]}>
      {formatRoleChip(role)}
    </span>
  );
}

export function RoleLegend({ roles = ["designed", "executed", "predicted", "measured"] }: { roles?: DataRole[] }) {
  return (
    <div className="role-legend">
      {roles.map((role) => <RoleBadge key={role} role={role} />)}
    </div>
  );
}
