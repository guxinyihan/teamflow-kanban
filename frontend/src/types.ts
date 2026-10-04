export type TaskPriority = 'high' | 'medium' | 'low';
export type Role = 'owner' | 'admin' | 'member';
export type Visibility = 'private' | 'team' | 'public-read';
export interface User {
  id: number;
  username: string;
  full_name?: string | null;
  email?: string;
}
export interface Label {
  id: number;
  name: string;
  color: string;
}
export interface ChecklistItem {
  id: number;
  content: string;
  is_completed: boolean;
}
export interface Comment {
  id: number;
  content: string;
  created_at: string;
  user_id: number;
  user_name: string;
}
export interface Attachment {
  id: number;
  filename: string;
  created_at: string;
  size?: number;
}
export interface Task {
  id: number;
  board_id: number;
  column_id: number;
  title: string;
  description?: string;
  priority: TaskPriority;
  position: number;
  version: number;
  is_archived: boolean;
  due_date?: string | null;
  assignee_id?: number | null;
  assigned_to: User[];
  labels: Label[];
  comments: Comment[];
  checklist: ChecklistItem[];
  attachments: Attachment[];
  created_at: string;
}
export interface Column {
  id: number;
  name: string;
  position: number;
  wip_limit: number | null;
  active_count: number;
}
export interface TeamMember {
  role: Role;
  user: User;
}
export interface Team {
  id: number;
  name: string;
  description?: string;
  role: Role;
  owner_id: number;
  members?: TeamMember[];
}
export interface BoardMember {
  user: User;
  role: 'member' | 'admin';
}
export interface Board {
  id: number;
  team_id: number;
  name: string;
  description?: string;
  visibility: Visibility;
  revision: number;
  can_edit: boolean;
  can_admin: boolean;
  members?: BoardMember[];
}
export interface BoardState {
  board: Board;
  columns: Column[];
  tasks: Task[];
  members: User[];
  revision: number;
  permissions: { can_edit: boolean; can_admin: boolean };
}
export interface Activity {
  id: number;
  actor_name: string;
  action: string;
  entity_type: string;
  entity_id: number;
  created_at: string;
  details: Record<string, unknown>;
}
export interface Invitation {
  id: number;
  email: string;
  role: 'member' | 'admin';
  expires_at: string;
  accepted_at?: string | null;
  revoked_at?: string | null;
  token?: string;
  invitation_url?: string;
}
export interface TaskCreateInput {
  title: string;
  description?: string;
  column_id: number;
  priority?: TaskPriority;
  due_date?: string | null;
  assignee_id?: number | null;
}
export type TaskUpdateInput = Partial<Omit<TaskCreateInput, 'column_id'>> & {
  is_archived?: boolean;
};
