import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DragDropContext, Droppable } from '@hello-pangea/dnd';
import { AxiosError } from 'axios';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'react-hot-toast';
import * as api from '../services/api';
import * as auth from '../services/auth';
import { useTaskMove } from '../hooks/useTaskMove';
import { useBoardSocket } from '../hooks/useBoardSocket';
import { AuthProvider } from '../contexts/AuthContext';
import { useAuth } from '../contexts/authState';
import { TaskCard } from '../components/TaskCard';
import { TaskDetailsModal } from '../components/TaskDetailsModal';
import { InviteForm } from '../components/TeamSettings';
import { ActivityPanel } from '../components/ActivityPanel';
import { boardState, task, team } from './fixtures';
import type { BoardState } from '../types';

function environment() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  };
}
function conflict(code: string) {
  return new AxiosError('Conflict', 'ERR_BAD_REQUEST', undefined, undefined, {
    status: 409,
    statusText: 'Conflict',
    headers: {},
    config: { headers: {} } as never,
    data: { detail: { code, message: 'The destination is full', revision: 8 } },
  });
}

class TestSocket {
  static instances: TestSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor(url: string | URL) {
    this.url = String(url);
    TestSocket.instances.push(this);
  }
  message(value: object) {
    this.onmessage?.({ data: JSON.stringify(value) });
  }
}

beforeEach(() => {
  api.endSession();
  localStorage.clear();
  sessionStorage.clear();
  TestSocket.instances = [];
  vi.stubGlobal('WebSocket', TestSocket);
});

describe('permissions and invitations', () => {
  it('shows keyboard move controls only for an editor', () => {
    const props = {
      task,
      index: 0,
      columns: boardState.columns,
      moving: false,
      onOpen: vi.fn(),
      onMove: vi.fn(),
    };
    const view = render(
      <DragDropContext onDragEnd={vi.fn()}>
        <Droppable droppableId="1">
          {(provided) => (
            <div ref={provided.innerRef} {...provided.droppableProps}>
              <TaskCard {...props} canEdit={false} />
              {provided.placeholder}
            </div>
          )}
        </Droppable>
      </DragDropContext>,
    );
    expect(screen.getByRole('button', { name: task.title })).toBeEnabled();
    expect(screen.queryByLabelText(`Move ${task.title} to column`)).not.toBeInTheDocument();
    view.rerender(
      <DragDropContext onDragEnd={vi.fn()}>
        <Droppable droppableId="1">
          {(provided) => (
            <div ref={provided.innerRef} {...provided.droppableProps}>
              <TaskCard {...props} canEdit />
              {provided.placeholder}
            </div>
          )}
        </Droppable>
      </DragDropContext>,
    );
    expect(screen.getByLabelText(`Move ${task.title} to column`)).toBeEnabled();
    expect(screen.getByRole('button', { name: `Move ${task.title} up` })).toBeDisabled();
  });
  it('makes task details read only for a public reader', () => {
    render(
      <TaskDetailsModal
        task={task}
        members={[]}
        canEdit={false}
        canAdmin={false}
        userId={10}
        onClose={vi.fn()}
        onChange={vi.fn()}
        onDeleted={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('Title')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Post comment' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Upload PDF/)).not.toBeInTheDocument();
  });
  it('posts an account-bound invitation with the selected role', async () => {
    const invite = {
      id: 8,
      email: 'member@example.test',
      role: 'admin' as const,
      token: 'only-shown-once',
      expires_at: '2026-10-04T10:00:00Z',
    };
    const create = vi.spyOn(api, 'inviteMember').mockResolvedValue(invite);
    const onCreated = vi.fn();
    render(<InviteForm team={team} onCreated={onCreated} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Email'), invite.email);
    await user.selectOptions(screen.getByLabelText('Role'), 'admin');
    await user.click(screen.getByRole('button', { name: 'Create invitation' }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(invite));
    expect(create).toHaveBeenCalledWith(1, invite.email, 'admin');
    expect(localStorage.length).toBe(0);
  });
  it('prevents normal members from seeing the invite form and admins from assigning admin', () => {
    const view = render(<InviteForm team={{ ...team, role: 'member' }} onCreated={vi.fn()} />);
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument();
    view.rerender(<InviteForm team={{ ...team, role: 'admin' }} onCreated={vi.fn()} />);
    expect(screen.queryByRole('option', { name: 'Admin' })).not.toBeInTheDocument();
  });
  it('keeps rejected invitation errors visible without claiming success', async () => {
    vi.spyOn(api, 'inviteMember').mockRejectedValue(conflict('already_invited'));
    const onCreated = vi.fn();
    render(<InviteForm team={team} onCreated={onCreated} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Email'), 'member@example.test');
    await user.click(screen.getByRole('button', { name: 'Create invitation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The destination is full');
    expect(onCreated).not.toHaveBeenCalled();
  });
});

describe('atomic move reconciliation', () => {
  it.each(['wip_limit', 'stale_revision'])(
    'rolls back %s conflicts and invalidates the authoritative board',
    async (code) => {
      const { client, wrapper } = environment();
      const key = ['user', 1, 'board', 1];
      client.setQueryData(key, boardState);
      const invalidate = vi.spyOn(client, 'invalidateQueries');
      const notify = vi.spyOn(toast, 'error').mockReturnValue('1');
      let reject!: (reason: unknown) => void;
      const request = vi.spyOn(api, 'moveTask').mockImplementation(
        () =>
          new Promise((_resolve, rejectPromise) => {
            reject = rejectPromise;
          }),
      );
      const { result } = renderHook(() => useTaskMove(1, key, ['user', 1, 'activity', 1]), {
        wrapper,
      });
      act(() =>
        result.current.mutate({ taskId: 1, columnId: 2, index: 1, revision: 7, version: 3 }),
      );
      await waitFor(() => expect(client.getQueryData<BoardState>(key)?.tasks[0].column_id).toBe(2));
      expect(request).toHaveBeenCalledTimes(1);
      expect(request).toHaveBeenCalledWith(1, {
        target_column_id: 2,
        target_index: 1,
        expected_revision: 7,
        expected_version: 3,
      });
      await act(async () => reject(conflict(code)));
      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(client.getQueryData(key)).toEqual(boardState);
      expect(invalidate).toHaveBeenCalledWith({ queryKey: key });
      expect(notify).toHaveBeenCalledWith(expect.stringContaining('rolled back'));
      if (code === 'wip_limit')
        expect(notify).toHaveBeenCalledWith(expect.stringContaining('WIP limit reached'));
    },
  );
  it('adopts the revision and version from a committed move', async () => {
    const { client, wrapper } = environment();
    const key = ['user', 1, 'board', 1];
    client.setQueryData(key, boardState);
    vi.spyOn(api, 'moveTask').mockResolvedValue({
      task: { ...task, column_id: 2, position: 1, version: 4 },
      revision: 8,
    });
    const { result } = renderHook(() => useTaskMove(1, key, ['activity', 1]), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        taskId: 1,
        columnId: 2,
        index: 1,
        revision: 7,
        version: 3,
      });
    });
    expect(client.getQueryData<BoardState>(key)?.revision).toBe(8);
    expect(client.getQueryData<BoardState>(key)?.tasks[0].version).toBe(4);
  });
  it('does not restore an old user cache when an in-flight move fails after logout', async () => {
    const { client, wrapper } = environment();
    const key = ['user', 1, 'board', 1];
    api.setAccessToken('owner-token');
    client.setQueryData(key, boardState);
    let reject!: (reason: unknown) => void;
    vi.spyOn(api, 'moveTask').mockImplementation(
      () =>
        new Promise((_resolve, failure) => {
          reject = failure;
        }),
    );
    const { result } = renderHook(() => useTaskMove(1, key, ['activity', 1]), { wrapper });
    act(() => result.current.mutate({ taskId: 1, columnId: 2, index: 1, revision: 7, version: 3 }));
    await waitFor(() => expect(client.getQueryData<BoardState>(key)?.tasks[0].column_id).toBe(2));
    act(() => {
      api.endSession();
      client.clear();
      api.setAccessToken('member-token');
    });
    await act(async () => reject(conflict('wip_limit')));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(client.getQueryData(key)).toBeUndefined();
  });
  it('preserves a newer authoritative snapshot when an older mutation response arrives', async () => {
    const { client, wrapper } = environment();
    const key = ['user', 1, 'board', 1];
    client.setQueryData(key, boardState);
    let resolve!: (response: { task: typeof task; revision: number }) => void;
    vi.spyOn(api, 'moveTask').mockImplementation(
      () =>
        new Promise((success) => {
          resolve = success;
        }),
    );
    const { result } = renderHook(() => useTaskMove(1, key, ['activity', 1]), { wrapper });
    act(() => result.current.mutate({ taskId: 1, columnId: 2, index: 1, revision: 7, version: 3 }));
    await waitFor(() => expect(client.getQueryData<BoardState>(key)?.tasks[0].column_id).toBe(2));
    const newer = {
      ...boardState,
      revision: 9,
      tasks: [{ ...task, title: 'Latest title' }, boardState.tasks[1]],
    };
    client.setQueryData(key, newer);
    await act(async () => resolve({ task: { ...task, column_id: 2, version: 4 }, revision: 8 }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryData(key)).toEqual(newer);
  });
});

describe('authenticated realtime and logout', () => {
  it('authenticates in the first message, refetches same-board events and closes on logout', () => {
    const { client, wrapper } = environment();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    api.setAccessToken('session-secret');
    const { unmount } = renderHook(
      () => useBoardSocket(1, 1, ['user', 1, 'board', 1], ['user', 1, 'activity', 1]),
      { wrapper },
    );
    const socket = TestSocket.instances[0];
    expect(socket.url).toBe('ws://localhost:8000/api/boards/1/ws');
    expect(socket.url).not.toContain('session-secret');
    act(() => socket.onopen?.());
    expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ token: 'session-secret' }));
    act(() => socket.message({ type: 'ready', board_id: 1, revision: 7 }));
    expect(invalidate).toHaveBeenCalledTimes(2);
    act(() => socket.message({ type: 'ping', board_id: 1 }));
    expect(invalidate).toHaveBeenCalledTimes(2);
    act(() => socket.message({ type: 'task.moved', board_id: 2, revision: 9 }));
    expect(invalidate).toHaveBeenCalledTimes(2);
    act(() => socket.message({ type: 'task.moved', board_id: 1, revision: 8 }));
    expect(invalidate).toHaveBeenCalledTimes(4);
    act(() => api.endSession());
    expect(socket.close).toHaveBeenCalledTimes(1);
    act(() => socket.message({ type: 'task.created', board_id: 1, revision: 9 }));
    expect(invalidate).toHaveBeenCalledTimes(4);
    unmount();
  });
  it('reconnects after interruption and refetches on the next authenticated ready', async () => {
    vi.useFakeTimers();
    try {
      const { client, wrapper } = environment();
      const invalidate = vi.spyOn(client, 'invalidateQueries');
      api.setAccessToken('secret');
      const { result, unmount } = renderHook(
        () => useBoardSocket(1, 1, ['board', 1], ['activity', 1]),
        { wrapper },
      );
      act(() => TestSocket.instances[0].onclose?.({ code: 1006 }));
      expect(result.current).toBe('Reconnecting');
      act(() => vi.advanceTimersByTime(1000));
      expect(TestSocket.instances).toHaveLength(2);
      act(() => TestSocket.instances[1].onopen?.());
      act(() => TestSocket.instances[1].message({ type: 'ready', board_id: 1, revision: 9 }));
      expect(result.current).toBe('Live');
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['board', 1] });
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });
  it('does not retry an authorization-rejected channel', () => {
    vi.useFakeTimers();
    try {
      const { wrapper } = environment();
      api.setAccessToken('secret');
      const { result } = renderHook(() => useBoardSocket(1, 1, ['board', 1], ['activity', 1]), {
        wrapper,
      });
      act(() => TestSocket.instances[0].onclose?.({ code: 1008 }));
      act(() => vi.advanceTimersByTime(60000));
      expect(result.current).toBe('Access ended');
      expect(TestSocket.instances).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });
  it('clears all user-scoped caches, closes sockets and prevents a later account from seeing old data', async () => {
    const { client, wrapper: QueryWrapper } = environment();
    vi.spyOn(auth, 'login')
      .mockResolvedValueOnce({
        access_token: 'owner-token',
        token_type: 'bearer',
        user: { id: 1, username: 'owner', email: 'owner@example.test', full_name: null },
      })
      .mockResolvedValueOnce({
        access_token: 'member-token',
        token_type: 'bearer',
        user: { id: 2, username: 'member', email: 'member@example.test', full_name: null },
      });
    function Session() {
      const state = useAuth();
      useBoardSocket(
        state.user ? 1 : null,
        state.user?.id || 0,
        ['user', state.user?.id, 'board', 1],
        ['activity'],
      );
      return (
        <>
          <span>{state.user?.username || 'Signed out'}</span>
          <button onClick={() => void state.login({ username: 'test', password: 'password' })}>
            Sign in
          </button>
          <button onClick={state.logout}>Log out</button>
        </>
      );
    }
    render(
      <QueryWrapper>
        <AuthProvider>
          <Session />
        </AuthProvider>
      </QueryWrapper>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByText('Sign in'));
    expect(await screen.findByText('owner')).toBeInTheDocument();
    client.setQueryData(['user', 1, 'board', 1], { private: 'owner data' });
    expect(api.getAccessToken()).toBe('owner-token');
    expect(localStorage.getItem('token')).toBeNull();
    const socket = TestSocket.instances[TestSocket.instances.length - 1];
    await user.click(screen.getByText('Log out'));
    expect(screen.getByText('Signed out')).toBeInTheDocument();
    expect(client.getQueryCache().getAll()).toHaveLength(0);
    expect(api.getAccessToken()).toBeNull();
    expect(socket.close).toHaveBeenCalled();
    await user.click(screen.getByText('Sign in'));
    expect(await screen.findByText('member')).toBeInTheDocument();
    expect(client.getQueryData(['user', 1, 'board', 1])).toBeUndefined();
    expect(api.getAccessToken()).toBe('member-token');
  });
});

describe('activity and private attachment access', () => {
  it('names columns, WIP changes and assignment targets from persisted event details', () => {
    const base = { actor_name: 'Project Owner', created_at: new Date().toISOString() };
    render(
      <ActivityPanel
        events={[
          {
            ...base,
            id: 1,
            action: 'wip_limit_changed',
            entity_type: 'column',
            entity_id: 7,
            details: { name: 'Review', wip_limit: 2 },
          },
          {
            ...base,
            id: 2,
            action: 'task_assigned',
            entity_type: 'task',
            entity_id: 5,
            details: { title: 'API Integration', assignee_name: 'Invited Member' },
          },
          {
            ...base,
            id: 3,
            action: 'wip_limit_changed',
            entity_type: 'column',
            entity_id: 8,
            details: { name: 'Done', wip_limit: null },
          },
        ]}
      />,
    );
    expect(screen.getByText('Review')).toBeInTheDocument();
    expect(screen.getByText('WIP limit: 2')).toBeInTheDocument();
    expect(screen.getByText('API Integration')).toBeInTheDocument();
    expect(screen.getByText('Assignee: Invited Member')).toBeInTheDocument();
    expect(screen.getByText('WIP limit: Unlimited')).toBeInTheDocument();
  });
  it('renders actor, action and task from actual event records', () => {
    render(
      <ActivityPanel
        events={[
          {
            id: 19,
            actor_name: 'Project Owner',
            action: 'task_moved',
            entity_type: 'task',
            entity_id: 1,
            created_at: new Date().toISOString(),
            details: { title: 'API Integration', from_column: 'Todo', to_column: 'In Progress' },
          },
        ]}
      />,
    );
    expect(screen.getByText('Project Owner')).toBeInTheDocument();
    expect(screen.getByText(/task moved/)).toBeInTheDocument();
    expect(screen.getByText('API Integration')).toBeInTheDocument();
    expect(screen.getByText('Todo → In Progress')).toBeInTheDocument();
  });
  it('shows an honest empty activity state', () => {
    render(<ActivityPanel events={[]} />);
    expect(screen.getByText('No recorded activity yet.')).toBeInTheDocument();
  });
  it('fetches private downloads through the authenticated API before creating a temporary blob', async () => {
    vi.spyOn(api.api, 'get').mockResolvedValue({ data: new Blob(['safe text']) });
    const create = vi.fn(() => 'blob:private-file');
    vi.stubGlobal(
      'URL',
      class extends URL {
        static createObjectURL = create;
        static revokeObjectURL = vi.fn();
      },
    );
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await api.downloadAttachment({
      id: 12,
      filename: 'requirements.txt',
      created_at: '2026-10-03T10:00:00Z',
    });
    expect(api.api.get).toHaveBeenCalledWith('/attachments/12/download', { responseType: 'blob' });
    expect(create).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(document.querySelector('a[download]')).toBeNull();
  });
});
