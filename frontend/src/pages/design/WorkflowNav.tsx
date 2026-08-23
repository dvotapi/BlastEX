import { formatRoleChip, WORKFLOW_STAGES, type WorkflowStageId } from "../../lib/lifecycle";

export function WorkflowNav({
  stage,
  onStageChange,
}: {
  stage: WorkflowStageId;
  onStageChange: (stage: WorkflowStageId) => void;
}) {
  return (
    <nav className="workflow-nav" aria-label="Инженерный маршрут">
      {WORKFLOW_STAGES.map((item, index) => (
        <button
          key={item.id}
          type="button"
          className={item.id === stage ? "active" : ""}
          onClick={() => onStageChange(item.id)}
          title={formatRoleChip(item.role)}
        >
          <small>{String(index + 1).padStart(2, "0")}</small>
          {item.label}
        </button>
      ))}
    </nav>
  );
}
