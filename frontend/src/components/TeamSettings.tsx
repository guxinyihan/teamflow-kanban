import { useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { Team, Invitation } from '../types';
import * as api from '../services/api';
import { Modal } from './Modal';

export function InviteForm({
  team,
  onCreated,
}: {
  team: Team;
  onCreated: (invite: Invitation) => void;
}) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'member' | 'admin'>('member');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const invite = await api.inviteMember(team.id, email.trim(), role);
      onCreated(invite);
      setEmail('');
    } catch (e) {
      setError(api.errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  if (team.role === 'member') return null;
  return (
    <form className="stack" onSubmit={submit}>
      <h3>Invite a teammate</h3>
      <div className="form-grid">
        <label htmlFor="invite-email">
          Email
          <input
            id="invite-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label htmlFor="invite-role">
          Role
          <select
            id="invite-role"
            value={role}
            onChange={(e) => setRole(e.target.value as 'member' | 'admin')}
          >
            <option value="member">Member</option>
            {team.role === 'owner' ? <option value="admin">Admin</option> : null}
          </select>
        </label>
      </div>
      {error ? (
        <p role="alert" className="error">
          {error}
        </p>
      ) : null}
      <div className="actions">
        <button className="primary" disabled={busy}>
          {busy ? 'Creating…' : 'Create invitation'}
        </button>
      </div>
    </form>
  );
}
export function TeamSettings({
  team,
  userId,
  onClose,
  onDeleted,
}: {
  team: Team;
  userId: number;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const client = useQueryClient();
  const [created, setCreated] = useState<Invitation | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState(team.name);
  const [description, setDescription] = useState(team.description || '');
  const prefix = ['user', userId];
  const canAdmin = team.role === 'owner' || team.role === 'admin';
  const detail = useQuery({
    queryKey: [...prefix, 'team', team.id],
    queryFn: ({ signal }) => api.getTeam(team.id, signal),
  });
  const invites = useQuery({
    queryKey: [...prefix, 'invitations', team.id],
    queryFn: ({ signal }) => api.getInvitations(team.id, signal),
    enabled: canAdmin,
  });
  async function refresh() {
    await client.invalidateQueries({ queryKey: prefix });
  }
  async function run(action: () => Promise<unknown>, done?: () => void) {
    setBusy(true);
    setError('');
    try {
      await action();
      await refresh();
      done?.();
    } catch (e) {
      setError(api.errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const inviteLink = created?.token
    ? `${window.location.origin}/?invite=${encodeURIComponent(created.token)}`
    : created?.invitation_url || '';
  return (
    <Modal title={`${team.name} · members & settings`} onClose={onClose} wide>
      <div className="stack">
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}
        {canAdmin ? (
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              void run(() => api.updateTeam(team.id, { name: name.trim(), description }));
            }}
          >
            <div className="form-grid">
              <label htmlFor="team-name">
                Team name
                <input
                  id="team-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={100}
                />
              </label>
              <label htmlFor="team-description">
                Description
                <input
                  id="team-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
            </div>
            <div className="actions">
              <button disabled={busy || !name.trim()}>Save team</button>
            </div>
          </form>
        ) : null}
        <section className="detail-section">
          <h3>Members</h3>
          {detail.isPending ? <p role="status">Loading members…</p> : null}
          {detail.error ? (
            <p role="alert" className="error">
              {api.errorMessage(detail.error)}
            </p>
          ) : null}
          {detail.data?.members?.map((member) => (
            <div className="member-row" key={member.user.id}>
              <div>
                <strong>{member.user.full_name || member.user.username}</strong>
                <span className="muted"> @{member.user.username}</span>
              </div>
              <span className="role-tag">{member.role}</span>
              {team.role === 'owner' && member.role !== 'owner' ? (
                <select
                  aria-label={`Role for ${member.user.username}`}
                  value={member.role}
                  disabled={busy}
                  onChange={(e) =>
                    void run(() =>
                      api.changeRole(team.id, member.user.id, e.target.value as 'member' | 'admin'),
                    )
                  }
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
              ) : null}
              {canAdmin &&
              member.role !== 'owner' &&
              (team.role === 'owner' || member.role === 'member') ? (
                <button
                  disabled={busy}
                  aria-label={`Remove ${member.user.username}`}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Remove ${member.user.username} from this team and its board memberships?`,
                      )
                    )
                      void run(() => api.removeTeamMember(team.id, member.user.id));
                  }}
                >
                  Remove
                </button>
              ) : null}
              {team.role === 'owner' && member.role !== 'owner' ? (
                <button
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Transfer ownership to ${member.user.username}? You will become an admin.`,
                      )
                    )
                      void run(() => api.transferOwnership(team.id, member.user.id), onClose);
                  }}
                >
                  Make owner
                </button>
              ) : null}
            </div>
          ))}
        </section>
        <InviteForm
          team={team}
          onCreated={(invite) => {
            setCreated(invite);
            void refresh();
          }}
        />
        {created ? (
          <div className="invite-created">
            <strong>Invitation created</strong>
            <p>
              The link is shown once. Share it with the invited account before{' '}
              {new Date(created.expires_at).toLocaleString()}.
            </p>
            <label htmlFor="invite-link">
              Invitation link
              <input
                id="invite-link"
                readOnly
                value={inviteLink}
                onFocus={(e) => e.target.select()}
              />
            </label>
            <button onClick={() => void run(() => navigator.clipboard.writeText(inviteLink))}>
              Copy invitation link
            </button>
          </div>
        ) : null}
        {canAdmin ? (
          <section className="detail-section">
            <h3>Invitations</h3>
            {invites.error ? (
              <p role="alert" className="error">
                {api.errorMessage(invites.error)}
              </p>
            ) : null}
            {invites.data?.length === 0 ? <p className="muted">No invitations yet.</p> : null}
            {invites.data?.map((invite) => {
              const pending =
                !invite.accepted_at &&
                !invite.revoked_at &&
                new Date(invite.expires_at) > new Date();
              return (
                <div className="resource-row" key={invite.id}>
                  <div>
                    {invite.email} <span className="role-tag">{invite.role}</span>
                    <small>
                      {invite.accepted_at
                        ? 'Accepted'
                        : invite.revoked_at
                          ? 'Revoked'
                          : pending
                            ? `Expires ${new Date(invite.expires_at).toLocaleDateString()}`
                            : 'Expired'}
                    </small>
                  </div>
                  {pending && (invite.role === 'member' || team.role === 'owner') ? (
                    <button
                      disabled={busy}
                      onClick={() => void run(() => api.revokeInvitation(invite.id))}
                    >
                      Revoke
                    </button>
                  ) : null}
                </div>
              );
            })}
          </section>
        ) : null}
        {team.role === 'owner' ? (
          <div className="actions task-danger">
            <button
              className="danger"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    `Permanently delete ${team.name}, all boards, tasks, comments, attachments, activity and invitations? This cannot be undone.`,
                  )
                )
                  void run(() => api.deleteTeam(team.id), onDeleted);
              }}
            >
              Delete team
            </button>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
