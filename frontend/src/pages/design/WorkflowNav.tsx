import { formatRoleChip, WORKFLOW_STAGES, type WorkflowStageId } from "../../lib/lifecycle";
import { STAGE_ICONS, type StageStatus } from "./workflowStatus";

const STATUS_LABEL: Record<StageStatus, string> = {
  empty: "не начато",
  ready: "готово",
  error: "есть ошибка",
  locked: "заблокировано",
};

export function WorkflowNav({
  stage,
  statuses,
  onStageChange,
}: {
  stage: WorkflowStageId;
  statuses: Record<WorkflowStageId, StageStatus>;
  onStageChange: (stage: WorkflowStageId) => void;
}) {
  return (
    <nav className="workflow-nav icons" aria-label="Инженерный маршрут">
      {WORKFLOW_STAGES.map((item) => {
        const status = statuses[item.id] ?? "empty";
        const active = item.id === stage;
        return (
          <button
            key={item.id}
            type="button"
            className={`${active ? "active" : ""} status-${status}`}
            onClick={() => onStageChange(item.id)}
            title={`${item.label} — ${STATUS_LABEL[status]} · ${formatRoleChip(item.role)}`}
            aria-current={active ? "step" : undefined}
          >
            <i aria-hidden="true">{STAGE_ICONS[item.id]}</i>
            <span>{item.label}</span>
            <em className={`stage-dot ${status}`} aria-hidden="true" />
          </button>
        );
      })}
    </nav>
  );
}
