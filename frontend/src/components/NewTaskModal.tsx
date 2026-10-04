import { useState, type FormEvent } from 'react';
import { Modal } from './Modal';
import type { User, TaskCreateInput } from '../types';
import { errorMessage } from '../services/api';
export function NewTaskModal({
  onClose,
  onSubmit,
  columnId,
  members,
}: {
  onClose: () => void;
  onSubmit: (input: TaskCreateInput) => Promise<void>;
  columnId: number;
  members: User[];
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [assignee, setAssignee] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onSubmit({
        title: title.trim(),
        description,
        column_id: columnId,
        assignee_id: assignee ? Number(assignee) : null,
      });
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Add task" onClose={onClose}>
      <form onSubmit={submit} className="stack">
        <label htmlFor="new-title">
          Title
          <input
            id="new-title"
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={200}
          />
        </label>
        <label htmlFor="new-description">
          Description
          <textarea
            id="new-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
          />
        </label>
        <label htmlFor="new-assignee">
          Assignee
          <select id="new-assignee" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
            <option value="">Unassigned</option>
            {members.map((member) => (
              <option key={member.id} value={member.id}>
                {member.full_name || member.username}
              </option>
            ))}
          </select>
        </label>
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}
        <div className="actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={busy || !title.trim()}>
            {busy ? 'Creating…' : 'Create task'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
