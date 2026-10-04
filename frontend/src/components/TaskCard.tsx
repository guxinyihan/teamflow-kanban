import { Draggable } from '@hello-pangea/dnd';
import { format, isPast, isToday } from 'date-fns';
import type { Task, Column } from '../types';
export interface TaskCardProps {
  task: Task;
  index: number;
  columns: Column[];
  canEdit: boolean;
  moving: boolean;
  dragDisabled?: boolean;
  onOpen: (id: number) => void;
  onMove: (id: number, column: number, index: number) => void;
}
export function TaskCard({
  task,
  index,
  columns,
  canEdit,
  moving,
  dragDisabled,
  onOpen,
  onMove,
}: TaskCardProps) {
  const completedItems = task.checklist.filter((item) => item.is_completed).length;
  const totalItems = task.checklist.length;
  const dueDate = task.due_date ? new Date(task.due_date) : null;
  const overdue = dueDate && isPast(dueDate) && !isToday(dueDate);
  const assignee = task.assigned_to?.[0];
  const ownColumn = columns.find((column) => column.id === task.column_id);
  return (
    <Draggable
      draggableId={String(task.id)}
      index={index}
      isDragDisabled={!canEdit || moving || dragDisabled || task.is_archived}
    >
      {(provided) => (
        <article
          ref={provided.innerRef}
          {...provided.draggableProps}
          className={`task-card priority-${task.priority}`}
        >
          <div className="task-top">
            <span className={`priority-tag ${task.priority}`}>{task.priority}</span>
            {canEdit && !task.is_archived ? (
              <span
                {...provided.dragHandleProps}
                className="drag-handle"
                aria-label={`Drag ${task.title}`}
              >
                ⠿
              </span>
            ) : null}
          </div>
          <h3>
            <button className="task-title-button" onClick={() => onOpen(task.id)}>
              {task.title}
            </button>
          </h3>
          {task.description ? <p className="task-preview">{task.description}</p> : null}
          {task.labels.length ? (
            <div className="labels">
              {task.labels.map((label) => (
                <span key={label.id} className="task-label" style={{ borderColor: label.color }}>
                  {label.name}
                </span>
              ))}
            </div>
          ) : null}
          <div className="task-metadata">
            {dueDate ? (
              <span className={overdue ? 'overdue' : ''}>
                {overdue ? 'Overdue · ' : ''}
                {format(dueDate, 'MMM d')}
              </span>
            ) : null}
            {task.comments.length ? <span>{task.comments.length} comments</span> : null}
            {task.attachments.length ? <span>{task.attachments.length} files</span> : null}
            {totalItems ? (
              <span>
                {completedItems}/{totalItems} done
              </span>
            ) : null}
          </div>
          {totalItems ? (
            <progress value={completedItems} max={totalItems} aria-label="Checklist completion" />
          ) : null}
          {assignee ? (
            <div className="assignee">
              <span className="avatar" aria-hidden="true">
                {(assignee.full_name || assignee.username).slice(0, 1).toUpperCase()}
              </span>
              {assignee.full_name || assignee.username}
            </div>
          ) : null}
          {canEdit && !task.is_archived ? (
            <div className="task-move">
              <button
                disabled={moving || task.position === 0}
                aria-label={`Move ${task.title} up`}
                onClick={() => onMove(task.id, task.column_id, task.position - 1)}
              >
                ↑
              </button>
              <button
                disabled={moving || task.position >= (ownColumn?.active_count || 0) - 1}
                aria-label={`Move ${task.title} down`}
                onClick={() => onMove(task.id, task.column_id, task.position + 1)}
              >
                ↓
              </button>
              <select
                aria-label={`Move ${task.title} to column`}
                value={task.column_id}
                disabled={moving}
                onChange={(event) =>
                  onMove(
                    task.id,
                    Number(event.target.value),
                    columns.find((column) => column.id === Number(event.target.value))
                      ?.active_count || 0,
                  )
                }
              >
                {columns.map((column) => (
                  <option key={column.id} value={column.id}>
                    {column.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
        </article>
      )}
    </Draggable>
  );
}
