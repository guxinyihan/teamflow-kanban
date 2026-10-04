import { useState, type FormEvent } from 'react';
import { format } from 'date-fns';
import type { Task, TaskPriority, User, TaskUpdateInput } from '../types';
import { Modal } from './Modal';
import * as api from '../services/api';

export function TaskDetailsModal({
  task,
  members,
  canEdit,
  canAdmin,
  userId,
  onClose,
  onChange,
  onDeleted,
}: {
  task: Task;
  members: User[];
  canEdit: boolean;
  canAdmin: boolean;
  userId: number;
  onClose: () => void;
  onChange: () => Promise<void>;
  onDeleted: () => void;
}) {
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description || '');
  const [priority, setPriority] = useState<TaskPriority>(task.priority);
  const [dueDate, setDueDate] = useState(task.due_date?.slice(0, 10) || '');
  const [assignee, setAssignee] = useState(task.assignee_id ? String(task.assignee_id) : '');
  const [comment, setComment] = useState('');
  const [checklist, setChecklist] = useState('');
  const [label, setLabel] = useState('');
  const [color, setColor] = useState('#2563eb');
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
  function save(event: FormEvent) {
    event.preventDefault();
    const input: TaskUpdateInput = {
      title: title.trim(),
      description,
      priority,
      due_date: dueDate ? `${dueDate}T00:00:00` : null,
      assignee_id: assignee ? Number(assignee) : null,
    };
    void run(() => api.updateTask(task.id, input));
  }
  return (
    <Modal title={canEdit ? 'Task details' : 'Task details · read only'} onClose={onClose} wide>
      <div className="stack">
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}
        <form onSubmit={save} className="stack">
          <fieldset disabled={!canEdit || busy}>
            <label htmlFor="task-title">
              Title
              <input
                id="task-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                maxLength={200}
              />
            </label>
            <label htmlFor="task-description">
              Description
              <textarea
                id="task-description"
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <div className="form-grid">
              <label htmlFor="task-priority">
                Priority
                <select
                  id="task-priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as TaskPriority)}
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </label>
              <label htmlFor="task-date">
                Due date
                <input
                  id="task-date"
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                />
              </label>
              <label htmlFor="task-assignee">
                Assignee
                <select
                  id="task-assignee"
                  value={assignee}
                  onChange={(e) => setAssignee(e.target.value)}
                >
                  <option value="">Unassigned</option>
                  {members.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.full_name || member.username}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {canEdit ? (
              <div className="actions">
                <button className="primary" disabled={!title.trim()}>
                  Save changes
                </button>
              </div>
            ) : null}
          </fieldset>
        </form>
        <section className="detail-section">
          <h3>Checklist</h3>
          {task.checklist.map((item) => (
            <div key={item.id} className="resource-row">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={item.is_completed}
                  disabled={!canEdit || busy}
                  onChange={() => void run(() => api.toggleChecklistItem(task.id, item.id))}
                />
                {item.content}
              </label>
              {canEdit ? (
                <button
                  className="text-button"
                  disabled={busy}
                  aria-label={`Remove checklist item ${item.content}`}
                  onClick={() => void run(() => api.removeChecklistItem(task.id, item.id))}
                >
                  Remove
                </button>
              ) : null}
            </div>
          ))}
          {canEdit ? (
            <form
              className="inline-form"
              onSubmit={(e) => {
                e.preventDefault();
                void run(
                  () => api.addChecklistItem(task.id, checklist.trim()),
                  () => setChecklist(''),
                );
              }}
            >
              <label className="sr-only" htmlFor="checklist-input">
                New checklist item
              </label>
              <input
                id="checklist-input"
                placeholder="Add a checklist item"
                value={checklist}
                onChange={(e) => setChecklist(e.target.value)}
                required
              />
              <button disabled={busy || !checklist.trim()}>Add item</button>
            </form>
          ) : null}
        </section>
        <section className="detail-section">
          <h3>Labels</h3>
          <div className="labels">
            {task.labels.map((item) => (
              <span key={item.id} className="task-label" style={{ borderColor: item.color }}>
                {item.name}
                {canEdit ? (
                  <button
                    disabled={busy}
                    aria-label={`Remove label ${item.name}`}
                    onClick={() => void run(() => api.removeLabel(task.id, item.id))}
                  >
                    ×
                  </button>
                ) : null}
              </span>
            ))}
          </div>
          {canEdit ? (
            <form
              className="inline-form"
              onSubmit={(e) => {
                e.preventDefault();
                void run(
                  () => api.addLabel(task.id, { name: label.trim(), color }),
                  () => setLabel(''),
                );
              }}
            >
              <label className="sr-only" htmlFor="label-input">
                New label
              </label>
              <input
                id="label-input"
                placeholder="New label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                maxLength={50}
              />
              <input
                type="color"
                aria-label="Label color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
              />
              <button disabled={busy || !label.trim()}>Add label</button>
            </form>
          ) : null}
        </section>
        <section className="detail-section">
          <h3>Private attachments</h3>
          {task.attachments.map((attachment) => (
            <div key={attachment.id} className="resource-row">
              <button
                className="text-button attachment-name"
                disabled={busy}
                onClick={() => void run(() => api.downloadAttachment(attachment))}
              >
                {attachment.filename}
              </button>
              {canEdit ? (
                <button
                  disabled={busy}
                  aria-label={`Delete attachment ${attachment.filename}`}
                  onClick={() => {
                    if (window.confirm(`Delete ${attachment.filename}?`))
                      void run(() => api.deleteAttachment(task.id, attachment.id));
                  }}
                >
                  Delete
                </button>
              ) : null}
            </div>
          ))}
          {canEdit ? (
            <label htmlFor="attachment-upload">
              Upload PDF, text, PNG or JPEG (up to 10 MiB)
              <input
                id="attachment-upload"
                type="file"
                accept=".pdf,.txt,.png,.jpg,.jpeg"
                disabled={busy}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) {
                    if (file.size > 10 * 1024 * 1024)
                      setError('Attachments must be 10 MiB or smaller.');
                    else void run(() => api.addAttachment(task.id, file));
                  }
                  event.target.value = '';
                }}
              />
            </label>
          ) : null}
        </section>
        <section className="detail-section">
          <h3>Comments</h3>
          {task.comments.length === 0 ? <p className="muted">No comments yet.</p> : null}
          {task.comments.map((item) => (
            <article key={item.id} className="comment">
              <div className="resource-row">
                <strong>{item.user_name}</strong>
                <time dateTime={item.created_at}>
                  {format(new Date(item.created_at), 'MMM d, HH:mm')}
                </time>
              </div>
              <p>{item.content}</p>
              {canEdit && (canAdmin || item.user_id === userId) ? (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => void run(() => api.deleteComment(task.id, item.id))}
                >
                  Delete comment
                </button>
              ) : null}
            </article>
          ))}
          {canEdit ? (
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                void run(
                  () => api.addComment(task.id, comment.trim()),
                  () => setComment(''),
                );
              }}
            >
              <label htmlFor="new-comment">
                Add comment
                <textarea
                  id="new-comment"
                  rows={3}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  maxLength={10000}
                />
              </label>
              <div className="actions">
                <button disabled={busy || !comment.trim()}>Post comment</button>
              </div>
            </form>
          ) : null}
        </section>
        {canEdit ? (
          <div className="actions task-danger">
            <button
              disabled={busy}
              onClick={() =>
                void run(
                  () => api.updateTask(task.id, { is_archived: !task.is_archived }),
                  onDeleted,
                )
              }
            >
              {task.is_archived ? 'Restore task' : 'Archive task'}
            </button>
            <button
              className="danger"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    `Permanently delete “${task.title}” and its comments, checklist and attachments?`,
                  )
                )
                  void run(() => api.deleteTask(task.id), onDeleted);
              }}
            >
              Delete task
            </button>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
