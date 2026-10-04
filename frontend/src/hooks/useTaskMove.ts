import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import type { BoardState } from '../types';
import { errorMessage, getSessionVersion, moveTask } from '../services/api';
export function optimisticMove(
  state: BoardState,
  taskId: number,
  targetColumn: number,
  targetIndex: number,
): BoardState {
  const moved = state.tasks.find((task) => task.id === taskId);
  if (!moved) return state;
  const positions = new Map<number, { column_id: number; position: number }>();
  for (const columnId of new Set([moved.column_id, targetColumn])) {
    const tasks = state.tasks
      .filter((task) => !task.is_archived && task.column_id === columnId && task.id !== taskId)
      .sort((a, b) => a.position - b.position);
    if (columnId === targetColumn)
      tasks.splice(Math.max(0, Math.min(targetIndex, tasks.length)), 0, moved);
    tasks.forEach((task, position) => positions.set(task.id, { column_id: columnId, position }));
  }
  const tasks = state.tasks.map((task) =>
    positions.has(task.id) ? { ...task, ...positions.get(task.id) } : task,
  );
  return {
    ...state,
    tasks,
    columns: state.columns.map((column) => ({
      ...column,
      active_count: tasks.filter((task) => !task.is_archived && task.column_id === column.id)
        .length,
    })),
  };
}
export function useTaskMove(boardId: number, queryKey: QueryKey, activityKey: QueryKey) {
  const client = useQueryClient();
  const session = getSessionVersion();
  return useMutation({
    scope: { id: `board-move-${boardId}` },
    mutationFn: ({
      taskId,
      columnId,
      index,
      revision,
      version,
    }: {
      taskId: number;
      columnId: number;
      index: number;
      revision: number;
      version: number;
    }) => {
      if (getSessionVersion() !== session) throw new Error('Session ended');
      return moveTask(taskId, {
        target_column_id: columnId,
        target_index: index,
        expected_revision: revision,
        expected_version: version,
      });
    },
    onMutate: async (move) => {
      await client.cancelQueries({ queryKey });
      if (getSessionVersion() !== session) throw new Error('Session ended');
      const previous = client.getQueryData<BoardState>(queryKey);
      if (previous)
        client.setQueryData(
          queryKey,
          optimisticMove(previous, move.taskId, move.columnId, move.index),
        );
      return { previous, session };
    },
    onError: (error, _move, context) => {
      if (getSessionVersion() !== session) return;
      const current = client.getQueryData<BoardState>(queryKey);
      if (context?.previous && (!current || current.revision <= context.previous.revision))
        client.setQueryData(queryKey, context.previous);
      toast.error(errorMessage(error));
    },
    onSuccess: (result) => {
      if (getSessionVersion() !== session) return;
      client.setQueryData<BoardState>(queryKey, (previous) =>
        previous && previous.revision <= result.revision
          ? {
              ...previous,
              revision: result.revision,
              board: { ...previous.board, revision: result.revision },
              tasks: previous.tasks.map((task) =>
                task.id === result.task.id ? result.task : task,
              ),
            }
          : previous,
      );
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey });
      void client.invalidateQueries({ queryKey: activityKey });
    },
  });
}
