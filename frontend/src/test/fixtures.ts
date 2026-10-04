import type { BoardState, Task, Team } from '../types';
export const team: Team = {
  id: 1,
  name: 'CS Project Team',
  role: 'owner',
  owner_id: 1,
  members: [{ role: 'owner', user: { id: 1, username: 'owner', full_name: 'Project Owner' } }],
};
export const task: Task = {
  id: 1,
  board_id: 1,
  column_id: 1,
  title: 'API Integration',
  description: 'Connect the project API',
  priority: 'medium',
  position: 0,
  version: 3,
  is_archived: false,
  assignee_id: null,
  assigned_to: [],
  labels: [],
  comments: [],
  checklist: [],
  attachments: [],
  created_at: '2026-10-03T10:00:00Z',
};
export const boardState: BoardState = {
  board: {
    id: 1,
    team_id: 1,
    name: 'Software Engineering Project',
    visibility: 'team',
    revision: 7,
    can_admin: true,
    can_edit: true,
    members: [],
  },
  columns: [
    { id: 1, name: 'Todo', position: 0, wip_limit: null, active_count: 1 },
    { id: 2, name: 'In Progress', position: 1, wip_limit: 1, active_count: 1 },
  ],
  tasks: [task, { ...task, id: 2, title: 'Database Schema', column_id: 2 }],
  members: [{ id: 1, username: 'owner' }],
  revision: 7,
  permissions: { can_edit: true, can_admin: true },
};
