import { describe, expect, it } from 'vitest';
import { optimisticMove } from '../hooks/useTaskMove';
import type { BoardState } from '../types';

describe('task move ordering regression', () => {
  it('normalizes both source and destination without dropping or duplicating tasks', () => {
    const state = { revision: 7, columns: [{ id: 1 }, { id: 2 }], tasks: [
      { id: 1, column_id: 1, position: 0 },
      { id: 2, column_id: 1, position: 1 },
      { id: 3, column_id: 2, position: 0 },
      { id: 4, column_id: 1, position: 2, is_archived: true },
    ] } as BoardState;
    const next = optimisticMove(state, 1, 2, 0);
    expect(next.tasks.filter(t => !t.is_archived).map(t => [t.id, t.column_id, t.position])).toEqual([
      [1, 2, 0], [2, 1, 0], [3, 2, 1],
    ]);
    expect(next.revision).toBe(7);
    expect(state.tasks[1].position).toBe(1);
    expect(next.tasks[3]).toEqual(state.tasks[3]);
  });
});
