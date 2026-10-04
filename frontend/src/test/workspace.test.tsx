import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { beforeEach, expect, it, vi } from 'vitest';
import * as api from '../services/api';
import { AuthContext } from '../contexts/authState';
import Board from '../components/Board';
import App from '../App';
import { boardState, team } from './fixtures';

class Socket {
  static latest: Socket;
  onopen = null;
  onclose = null;
  onerror = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor() {
    Socket.latest = this;
  }
}
beforeEach(() => {
  vi.stubGlobal('WebSocket', Socket);
  api.endSession();
  api.setAccessToken('access-token');
  vi.spyOn(api, 'getUserTeams').mockResolvedValue([team]);
  vi.spyOn(api, 'getTeam').mockResolvedValue(team);
  vi.spyOn(api, 'getTeamBoards').mockResolvedValue([boardState.board]);
  vi.spyOn(api, 'getBoardState').mockResolvedValue(boardState);
});
function renderBoard(props: Parameters<typeof Board>[0] = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const auth = {
    user: { id: 1, username: 'owner', email: 'owner@example.test', full_name: 'Project Owner' },
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  };
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <AuthContext.Provider value={auth}>
          <Board {...props} />
        </AuthContext.Provider>
      </QueryClientProvider>,
    ),
  };
}
it('renders actual columns and WIP counts with admin and editor controls', async () => {
  renderBoard();
  expect(await screen.findByRole('heading', { name: boardState.board.name })).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'In Progress column' })).toHaveTextContent(
    'WIP limit reached',
  );
  expect(screen.getByRole('button', { name: 'Board settings' })).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: '+ Add task' })).toHaveLength(2);
});
it('lets a public reader inspect tasks and activity while hiding mutations', async () => {
  vi.spyOn(api, 'getUserTeams').mockResolvedValue([{ ...team, role: 'member' }]);
  vi.spyOn(api, 'getBoardState').mockResolvedValue({
    ...boardState,
    board: { ...boardState.board, visibility: 'public-read', can_admin: false, can_edit: false },
    permissions: { can_edit: false, can_admin: false },
    members: [],
  });
  renderBoard();
  await screen.findByRole('heading', { name: boardState.board.name });
  expect(screen.getByText('Read only · public-read')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Board settings' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '+ Add column' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '+ Add task' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Activity' })).toBeInTheDocument();
});
it('removes a cached private board from the visible workspace after access is revoked', async () => {
  const state = vi.spyOn(api, 'getBoardState');
  renderBoard();
  await screen.findByRole('heading', { name: boardState.board.name });
  state.mockRejectedValue(
    new AxiosError('Forbidden', 'ERR_BAD_REQUEST', undefined, undefined, {
      status: 403,
      statusText: 'Forbidden',
      headers: {},
      config: { headers: {} } as never,
      data: { detail: 'Board permission required' },
    }),
  );
  act(() =>
    Socket.latest.onmessage?.({
      data: JSON.stringify({ type: 'board.membership_changed', board_id: 1, revision: 8 }),
    }),
  );
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: 'API Integration' })).not.toBeInTheDocument(),
  );
  expect(screen.getByRole('alert')).toHaveTextContent('Board permission required');
  expect(screen.queryByRole('button', { name: 'Board settings' })).not.toBeInTheDocument();
});
it('accepts the real invitation response team_id and clears the temporary token', async () => {
  const accept = vi
    .spyOn(api, 'acceptInvitation')
    .mockResolvedValue({ team_id: 1, role: 'member' });
  const onInviteAccepted = vi.fn();
  renderBoard({ initialInviteToken: 'random-single-use-token', onInviteAccepted });
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Review invitation' }));
  expect(screen.getByLabelText('Invitation token')).toHaveValue('random-single-use-token');
  await user.click(
    screen
      .getAllByRole('button', { name: 'Accept invitation' })
      .find((button) => button.closest('form'))!,
  );
  await waitFor(() => expect(onInviteAccepted).toHaveBeenCalledOnce());
  expect(accept).toHaveBeenCalledWith('random-single-use-token');
  expect(screen.queryByLabelText('Invitation token')).not.toBeInTheDocument();
});
it('strips an invitation URL before sign-in while keeping the token out of storage', async () => {
  window.history.replaceState(null, '', '/?invite=secret-link-token');
  render(<App />);
  await waitFor(() => expect(window.location.search).toBe(''));
  expect(screen.getByRole('heading', { name: 'Sign in to your account' })).toBeInTheDocument();
  expect(localStorage.getItem('token')).toBeNull();
  expect(localStorage.getItem('invite')).toBeNull();
});
