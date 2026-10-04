/** Create a fresh acceptance board through public APIs in a disposable database.
 * Required: TEAMFLOW_ALLOW_DISPOSABLE_SEED=yes and TEAMFLOW_SEED_PATH.
 * Optional: TEAMFLOW_API_URL. The output contains identifiers, never bearer tokens.
 */
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';

assert.equal(process.env.TEAMFLOW_ALLOW_DISPOSABLE_SEED, 'yes');
assert.ok(process.env.TEAMFLOW_SEED_PATH, 'Set TEAMFLOW_SEED_PATH to an untracked JSON file');
const api = process.env.TEAMFLOW_API_URL || 'http://127.0.0.1:8000/api';
const password = 'TeamFlow-Demo-42!';
const run = Date.now().toString(36);
const users = {};
const usernames = {};

async function request(route, { token, body, method = 'GET', form } = {}) {
  const response = await fetch(`${api}${route}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: form || (body ? JSON.stringify(body) : undefined),
  });
  assert.ok(response.ok, `${method} ${route}: HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}

for (const role of ['owner', 'admin', 'member', 'outsider']) {
  const username = `e2e${role}${run}`;
  usernames[role] = username;
  await request('/auth/register', {
    method: 'POST',
    body: {
      username,
      email: `${username}@example.test`,
      full_name: role[0].toUpperCase() + role.slice(1),
      password,
    },
  });
  users[role] = await request('/auth/login', {
    method: 'POST',
    form: new URLSearchParams({ username, password }),
  });
}
const token = users.owner.access_token;
const team = await request('/teams', { token, method: 'POST', body: { name: 'CS Project Team' } });
const board = await request(`/teams/${team.id}/boards`, {
  token,
  method: 'POST',
  body: { name: 'Software Engineering Project', visibility: 'team' },
});
for (const role of ['admin', 'member']) {
  const invitation = await request(`/teams/${team.id}/invitations`, {
    token,
    method: 'POST',
    body: { email: `${usernames[role]}@example.test`, role },
  });
  await request('/invitations/accept', {
    token: users[role].access_token,
    method: 'POST',
    body: { token: invitation.token },
  });
}
const columns = await request(`/boards/${board.id}/columns`, { token });
const backlog = await request(`/boards/${board.id}/columns`, {
  token,
  method: 'POST',
  body: { name: 'Backlog' },
});
const review = await request(`/boards/${board.id}/columns`, {
  token,
  method: 'POST',
  body: { name: 'Review' },
});
const column_ids = [backlog.id, columns[0].id, columns[1].id, review.id, columns[2].id];
const snapshot = await request(`/boards/${board.id}/state`, { token });
await request(`/boards/${board.id}/columns/reorder`, {
  token,
  method: 'POST',
  body: { column_ids, expected_revision: snapshot.revision },
});
await request(`/columns/${columns[1].id}`, { token, method: 'PATCH', body: { wip_limit: 2 } });
const task_ids = [];
for (const [index, title] of [
  'Requirements Specification',
  'Database Schema',
  'Frontend Integration',
  'Backend Tests',
].entries()) {
  const task = await request(`/tasks?board_id=${board.id}`, {
    token,
    method: 'POST',
    body: {
      title,
      description: 'Collaborative software engineering project deliverable.',
      column_id: columns[0].id,
      priority: index === 1 ? 'high' : 'medium',
      assignee_id: users.member.user.id,
      due_date: '2026-10-15T00:00:00Z',
    },
  });
  task_ids.push(task.id);
}
await request(`/tasks/${task_ids[0]}/labels`, {
  token,
  method: 'POST',
  body: { name: 'Planning', color: '#2563eb' },
});
await request(`/tasks/${task_ids[0]}/checklist`, {
  token,
  method: 'POST',
  body: { content: 'Review acceptance criteria with the team' },
});
await request(`/tasks/${task_ids[0]}/comments`, {
  token,
  method: 'POST',
  body: { content: 'Ready for the team to review.' },
});
const file = new FormData();
file.append(
  'file',
  new Blob(['TeamFlow demo requirements\n'], { type: 'text/plain' }),
  'requirements.txt',
);
const attachment = await request(`/tasks/${task_ids[0]}/attachments/`, {
  token,
  method: 'POST',
  form: file,
});
const output = {
  team_id: team.id,
  board_id: board.id,
  task_ids,
  column_ids,
  usernames,
  users: Object.fromEntries(
    Object.entries(users).map(([role, session]) => [role, session.user.id]),
  ),
  attachment_id: attachment.id,
};
await mkdir(path.dirname(path.resolve(process.env.TEAMFLOW_SEED_PATH)), { recursive: true });
await writeFile(process.env.TEAMFLOW_SEED_PATH, JSON.stringify(output, null, 2));
console.log(
  'Created fake acceptance accounts and a fresh board; saved identifiers without tokens.',
);
