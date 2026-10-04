import { Droppable } from '@hello-pangea/dnd';
import type { Column as ColumnType, Task } from '../types';
import { TaskCard, type TaskCardProps } from './TaskCard';
interface Props extends Omit<TaskCardProps, 'task' | 'index'> {
  column: ColumnType;
  tasks: Task[];
  canAdmin: boolean;
  onAdd: (column: number) => void;
  onSettings: (column: number) => void;
}
export default function Column({
  column,
  tasks,
  canAdmin,
  onAdd,
  onSettings,
  ...cardProps
}: Props) {
  const full = column.wip_limit !== null && column.active_count >= column.wip_limit;
  return (
    <section className={`column ${full ? 'column-full' : ''}`} aria-label={`${column.name} column`}>
      <div className="column-header">
        <h2>{column.name}</h2>
        <span
          className="column-count"
          aria-label={`${column.active_count} active tasks${column.wip_limit ? `, WIP limit ${column.wip_limit}` : ''}`}
        >
          {column.active_count}
          {column.wip_limit !== null ? ` / ${column.wip_limit}` : ''}
        </span>
        {canAdmin ? (
          <button
            className="icon-button"
            aria-label={`Settings for ${column.name}`}
            onClick={() => onSettings(column.id)}
          >
            ⋯
          </button>
        ) : null}
      </div>
      {full ? <p className="wip-note">WIP limit reached</p> : null}
      <Droppable
        droppableId={String(column.id)}
        isDropDisabled={!cardProps.canEdit || cardProps.moving || cardProps.dragDisabled}
      >
        {(provided) => (
          <div ref={provided.innerRef} {...provided.droppableProps} className="column-content">
            {[...tasks]
              .sort((a, b) => a.position - b.position)
              .map((task, index) => (
                <TaskCard key={task.id} task={task} index={index} {...cardProps} />
              ))}
            {provided.placeholder}
            {tasks.length === 0 ? <p className="column-empty">No tasks here yet</p> : null}
          </div>
        )}
      </Droppable>
      {cardProps.canEdit ? (
        <button className="add-card-button" onClick={() => onAdd(column.id)}>
          + Add task
        </button>
      ) : null}
    </section>
  );
}
