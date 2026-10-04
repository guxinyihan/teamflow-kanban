import { useState } from 'react';
import type { BoardState, Team, Visibility, Column } from '../types';
import { Modal } from './Modal';
import * as api from '../services/api';
export function ColumnSettings({
  column,
  columns,
  revision,
  boardId,
  onClose,
  onChange,
}: {
  column?: Column;
  columns: Column[];
  revision: number;
  boardId: number;
  onClose: () => void;
  onChange: () => Promise<void>;
}) {
  const [name, setName] = useState(column?.name || '');
  const [limit, setLimit] = useState(column?.wip_limit ? String(column.wip_limit) : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(action: () => Promise<unknown>, close = false) {
    setBusy(true);
    setError('');
    try {
      await action();
      await onChange();
      if (close) onClose();
    } catch (e) {
      setError(api.errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  function reorder(direction: number) {
    if (!column) return;
    const ids = columns.map((item) => item.id);
    const index = ids.indexOf(column.id);
    const target = index + direction;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    void run(() => api.reorderColumns(boardId, ids, revision));
  }
  return (
    <Modal title={column ? 'Column settings' : 'Add column'} onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          const input = { name: name.trim(), wip_limit: limit ? Number(limit) : null };
          void run(
            () => (column ? api.updateColumn(column.id, input) : api.addColumn(boardId, input)),
            true,
          );
        }}
      >
        <label htmlFor="column-name">
          Column name
          <input
            id="column-name"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
          />
        </label>
        <label htmlFor="column-wip">
          WIP limit
          <input
            id="column-wip"
            type="number"
            min={1}
            max={10000}
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            placeholder="No limit"
          />
        </label>
        <p className="muted">
          The server counts active tasks and enforces this limit on creates, moves and restores.
        </p>
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}
        <div className="actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={busy || !name.trim()}>
            Save column
          </button>
        </div>
      </form>
      {column ? (
        <div className="stack detail-section">
          <div className="actions">
            <button disabled={busy || columns[0].id === column.id} onClick={() => reorder(-1)}>
              Move column left
            </button>
            <button
              disabled={busy || columns[columns.length - 1].id === column.id}
              onClick={() => reorder(1)}
            >
              Move column right
            </button>
          </div>
          <button
            className="danger"
            disabled={busy}
            onClick={() => {
              if (window.confirm(`Delete ${column.name}? Only an empty column can be deleted.`))
                void run(() => api.deleteColumn(column.id), true);
            }}
          >
            Delete empty column
          </button>
        </div>
      ) : null}
    </Modal>
  );
}
export function BoardSettings({
  state,
  team,
  onClose,
  onChange,
  onDeleted,
}: {
  state: BoardState;
  team?: Team;
  onClose: () => void;
  onChange: () => Promise<void>;
  onDeleted: () => void;
}) {
  const [name, setName] = useState(state.board.name);
  const [visibility, setVisibility] = useState(state.board.visibility);
  const [memberId, setMemberId] = useState('');
  const [role, setRole] = useState<'member' | 'admin'>('member');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(action: () => Promise<unknown>, done?: () => void) {
    setBusy(true);
    setError('');
    try {
      await action();
      await onChange();
      done?.();
    } catch (e) {
      setError(api.errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Board settings" onClose={onClose} wide>
      <div className="stack">
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => api.updateBoard(state.board.id, { name: name.trim(), visibility }));
          }}
        >
          <label htmlFor="board-name">
            Board name
            <input
              id="board-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={100}
            />
          </label>
          <label htmlFor="board-visibility">
            Visibility
            <select
              id="board-visibility"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as Visibility)}
            >
              <option value="private">Private · explicit board members</option>
              <option value="team">Team · team members</option>
              <option value="public-read">Public read · authenticated readers</option>
            </select>
          </label>
          <p className="muted">
            Public read grants viewing. Editing still requires team or board authorization.
          </p>
          <div className="actions">
            <button disabled={busy || !name.trim()}>Save board</button>
          </div>
        </form>
        <section className="detail-section">
          <h3>Explicit board members</h3>
          {state.board.members?.map((member) => (
            <div className="resource-row" key={member.user.id}>
              <span>
                {member.user.full_name || member.user.username} · {member.role}
              </span>
              <button
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    api.removeBoardMember(state.board.team_id, state.board.id, member.user.id),
                  )
                }
              >
                Remove board access
              </button>
            </div>
          ))}
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              void run(() =>
                api.setBoardMember(state.board.team_id, state.board.id, Number(memberId), role),
              );
            }}
          >
            <div className="form-grid">
              <label htmlFor="board-member">
                Team member
                <select
                  id="board-member"
                  value={memberId}
                  onChange={(e) => setMemberId(e.target.value)}
                  required
                >
                  <option value="">Select member</option>
                  {team?.members?.map((member) => (
                    <option key={member.user.id} value={member.user.id}>
                      {member.user.full_name || member.user.username}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor="board-member-role">
                Board role
                <select
                  id="board-member-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as 'member' | 'admin')}
                >
                  <option value="member">Member · edit tasks</option>
                  <option value="admin">Admin · manage board</option>
                </select>
              </label>
            </div>
            <div className="actions">
              <button disabled={busy || !memberId}>Grant board access</button>
            </div>
          </form>
        </section>
        <div className="actions task-danger">
          <button
            className="danger"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  `Permanently delete ${state.board.name} and all its tasks, comments, attachments and activity?`,
                )
              )
                void run(() => api.deleteBoard(state.board.id), onDeleted);
            }}
          >
            Delete board
          </button>
        </div>
      </div>
    </Modal>
  );
}
