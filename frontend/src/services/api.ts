import axios from 'axios';
import type {
  Activity,
  Attachment,
  Board,
  BoardState,
  Column,
  Invitation,
  Label,
  Task,
  TaskCreateInput,
  TaskUpdateInput,
  Team,
  Visibility,
} from '../types';

// Access-token-only sessions. Tokens and board data never enter browser storage.
let accessToken: string | null = null;
let sessionVersion = 0;
const sessionEndListeners = new Set<() => void>();
export const getAccessToken = () => accessToken;
export const getSessionVersion = () => sessionVersion;
export function onSessionEnd(listener: () => void) {
  sessionEndListeners.add(listener);
  return () => {
    sessionEndListeners.delete(listener);
  };
}
export function endSession() {
  accessToken = null;
  sessionVersion += 1;
  for (const listener of sessionEndListeners) listener();
}
export function setAccessToken(token: string) {
  accessToken = token;
  sessionVersion += 1;
}
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
});
api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      axios.isAxiosError(error) &&
      error.response?.status === 401 &&
      accessToken &&
      error.config?.headers?.get('Authorization') === `Bearer ${accessToken}`
    )
      endSession();
    return Promise.reject(error);
  },
);
export function errorMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'object' && detail !== null && typeof detail.message === 'string') {
      if (detail.code === 'wip_limit')
        return `WIP limit reached. ${detail.message} Your move was rolled back.`;
      if (detail.code === 'stale_revision' || detail.code === 'stale_version')
        return 'This board changed in another session. Your move was rolled back; the latest board is loading.';
      return detail.message;
    }
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail))
      return detail
        .map((item) => (typeof item?.msg === 'string' ? item.msg : 'Invalid input'))
        .join('. ');
    if (!error.response) return 'Connection failed. Check that the API is available and try again.';
  }
  return 'The operation could not be completed. Please try again.';
}
export const getUserTeams = async (signal?: AbortSignal): Promise<Team[]> =>
  (await api.get('/teams', { signal })).data;
export const getTeam = async (id: number, signal?: AbortSignal): Promise<Team> =>
  (await api.get(`/teams/${id}`, { signal })).data;
export const createTeam = async (data: { name: string; description?: string }): Promise<Team> =>
  (await api.post('/teams', data)).data;
export const updateTeam = async (id: number, data: { name: string; description?: string }) =>
  api.patch(`/teams/${id}`, data);
export const deleteTeam = async (id: number) => api.delete(`/teams/${id}`);
export const getTeamBoards = async (id: number, signal?: AbortSignal): Promise<Board[]> =>
  (await api.get(`/teams/${id}/boards`, { signal })).data;
export const createBoard = async (
  id: number,
  data: { name: string; description?: string; visibility: Visibility },
): Promise<Board> => (await api.post(`/teams/${id}/boards`, data)).data;
export const getBoardState = async (id: number, signal?: AbortSignal): Promise<BoardState> =>
  (await api.get(`/boards/${id}/state`, { signal })).data;
export const updateBoard = async (id: number, data: { name?: string; visibility?: Visibility }) =>
  api.patch(`/boards/${id}`, data);
export const deleteBoard = async (id: number) => api.delete(`/boards/${id}`);
export const createTask = async (boardId: number, data: TaskCreateInput): Promise<Task> =>
  (await api.post('/tasks', data, { params: { board_id: boardId } })).data;
export const updateTask = async (id: number, data: TaskUpdateInput): Promise<Task> =>
  (await api.put(`/tasks/${id}`, data)).data;
export const deleteTask = async (id: number) => api.delete(`/tasks/${id}`);
export const moveTask = async (
  id: number,
  data: {
    target_column_id: number;
    target_index: number;
    expected_revision: number;
    expected_version: number;
  },
): Promise<{ task: Task; revision: number }> => (await api.post(`/tasks/${id}/move`, data)).data;
export const addColumn = async (
  id: number,
  data: { name: string; wip_limit: number | null },
): Promise<Column> => (await api.post(`/boards/${id}/columns`, data)).data;
export const updateColumn = async (id: number, data: { name: string; wip_limit: number | null }) =>
  api.patch(`/columns/${id}`, data);
export const deleteColumn = async (id: number) => api.delete(`/columns/${id}`);
export const reorderColumns = async (id: number, column_ids: number[], expected_revision: number) =>
  api.post(`/boards/${id}/columns/reorder`, { column_ids, expected_revision });
export const addComment = async (id: number, content: string) =>
  api.post(`/tasks/${id}/comments`, { content });
export const deleteComment = async (id: number, commentId: number) =>
  api.delete(`/tasks/${id}/comments/${commentId}`);
export const addLabel = async (id: number, label: Omit<Label, 'id'>) =>
  api.post(`/tasks/${id}/labels`, label);
export const removeLabel = async (id: number, labelId: number) =>
  api.delete(`/tasks/${id}/labels/${labelId}`);
export const addChecklistItem = async (id: number, content: string) =>
  api.post(`/tasks/${id}/checklist`, { content });
export const toggleChecklistItem = async (id: number, item: number) =>
  api.put(`/tasks/${id}/checklist/${item}/toggle`);
export const removeChecklistItem = async (id: number, item: number) =>
  api.delete(`/tasks/${id}/checklist/${item}`);
export async function addAttachment(id: number, file: File): Promise<Attachment> {
  const data = new FormData();
  data.append('file', file);
  return (await api.post(`/tasks/${id}/attachments/`, data)).data;
}
export const deleteAttachment = async (id: number, attachment: number) =>
  api.delete(`/tasks/${id}/attachments/${attachment}`);
export async function downloadAttachment(attachment: Attachment) {
  const { data } = await api.get<Blob>(`/attachments/${attachment.id}/download`, {
    responseType: 'blob',
  });
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = attachment.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const getActivity = async (id: number, signal?: AbortSignal): Promise<Activity[]> =>
  (await api.get(`/boards/${id}/activity`, { signal })).data;
export const getInvitations = async (id: number, signal?: AbortSignal): Promise<Invitation[]> =>
  (await api.get(`/teams/${id}/invitations`, { signal })).data;
export const inviteMember = async (
  id: number,
  email: string,
  role: 'member' | 'admin',
): Promise<Invitation> => (await api.post(`/teams/${id}/invitations`, { email, role })).data;
export const revokeInvitation = async (id: number) => api.delete(`/invitations/${id}`);
export const acceptInvitation = async (token: string): Promise<{ team_id: number; role: string }> =>
  (await api.post('/invitations/accept', { token })).data;
export const changeRole = async (team: number, user: number, role: 'member' | 'admin') =>
  api.patch(`/teams/${team}/members/${user}`, { role });
export const removeTeamMember = async (team: number, user: number) =>
  api.delete(`/teams/${team}/members/${user}`);
export const transferOwnership = async (team: number, user_id: number) =>
  api.post(`/teams/${team}/transfer-ownership`, { user_id });
export const setBoardMember = async (
  teamId: number,
  id: number,
  user_id: number,
  role: 'member' | 'admin',
) => api.post(`/teams/${teamId}/boards/${id}/members`, { user_id, role });
export const removeBoardMember = async (teamId: number, id: number, user: number) =>
  api.delete(`/teams/${teamId}/boards/${id}/members/${user}`);
