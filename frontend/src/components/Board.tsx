import { useState, type FormEvent } from 'react';
import { DragDropContext, type DropResult } from '@hello-pangea/dnd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { useAuth } from '../contexts/authState';
import * as api from '../services/api';
import type { TaskCreateInput, Visibility } from '../types';
import Column from './Column';
import { NewTaskModal } from './NewTaskModal';
import { TaskDetailsModal } from './TaskDetailsModal';
import { Modal } from './Modal';
import { TeamSettings } from './TeamSettings';
import { BoardSettings, ColumnSettings } from './BoardSettings';
import { ActivityPanel } from './ActivityPanel';
import { useTaskMove } from '../hooks/useTaskMove';
import { useBoardSocket } from '../hooks/useBoardSocket';

export default function Board({
  initialInviteToken = '',
  onInviteAccepted = () => {},
}: {
  initialInviteToken?: string;
  onInviteAccepted?: () => void;
}) {
  const { user, logout } = useAuth();
  const client = useQueryClient();
  const userId = user!.id;
  const [teamSelection, setTeamSelection] = useState<number | null>(null);
  const [boardSelection, setBoardSelection] = useState<number | null>(null);
  const [directBoard, setDirectBoard] = useState<number | null>(null);
  const [modal, setModal] = useState<
    'team' | 'board' | 'new-team' | 'new-board' | 'activity' | 'open-board' | 'invite' | null
  >(null);
  const [addTaskColumn, setAddTaskColumn] = useState<number | null>(null);
  const [selectedTask, setSelectedTask] = useState<number | null>(null);
  const [columnSettings, setColumnSettings] = useState<number | 'new' | null>(null);
  const [search, setSearch] = useState('');
  const [label, setLabel] = useState('');
  const [archived, setArchived] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [visibility, setVisibility] = useState<Visibility>('team');
  const [boardNumber, setBoardNumber] = useState('');
  const [inviteToken, setInviteToken] = useState(initialInviteToken);
  const prefix = ['user', userId];
  const teams = useQuery({
    queryKey: [...prefix, 'teams'],
    queryFn: ({ signal }) => api.getUserTeams(signal),
  });
  const teamId =
    teamSelection && teams.data?.some((team) => team.id === teamSelection)
      ? teamSelection
      : (teams.data?.[0]?.id ?? null);
  const selectedTeam = teams.data?.find((team) => team.id === teamId);
  const teamDetails = useQuery({
    queryKey: [...prefix, 'team', teamId],
    queryFn: ({ signal }) => api.getTeam(teamId!, signal),
    enabled: teamId !== null,
  });
  const boards = useQuery({
    queryKey: [...prefix, 'boards', teamId],
    queryFn: ({ signal }) => api.getTeamBoards(teamId!, signal),
    enabled: teamId !== null,
  });
  const listedBoard =
    boardSelection && boards.data?.some((board) => board.id === boardSelection)
      ? boardSelection
      : (boards.data?.[0]?.id ?? null);
  const boardId = directBoard ?? listedBoard;
  const boardKey = [...prefix, 'board', boardId];
  const activityKey = [...prefix, 'activity', boardId];
  const board = useQuery({
    queryKey: boardKey,
    queryFn: ({ signal }) => api.getBoardState(boardId!, signal),
    enabled: boardId !== null,
  });
  // A denied snapshot must not leave an old private board visible from cache.
  const state = board.isError ? undefined : board.data;
  const canEdit = state?.permissions.can_edit ?? false;
  const canAdmin = state?.permissions.can_admin ?? false;
  const activity = useQuery({
    queryKey: activityKey,
    queryFn: ({ signal }) => api.getActivity(boardId!, signal),
    enabled: boardId !== null && modal === 'activity',
  });
  const connection = useBoardSocket(state ? boardId : null, userId, boardKey, activityKey);
  const movement = useTaskMove(boardId || 0, boardKey, activityKey);
  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: boardKey }),
      client.invalidateQueries({ queryKey: activityKey }),
      client.invalidateQueries({ queryKey: [...prefix, 'boards', teamId] }),
    ]);
  }
  function move(id: number, columnId: number, index: number) {
    const task = state?.tasks.find((item) => item.id === id);
    if (!state || !task || !canEdit || movement.isPending) return;
    movement.mutate({
      taskId: id,
      columnId,
      index,
      revision: state.revision,
      version: task.version,
    });
  }
  function onDragEnd({ destination, source, draggableId }: DropResult) {
    if (
      !destination ||
      (destination.droppableId === source.droppableId && destination.index === source.index)
    )
      return;
    move(Number(draggableId), Number(destination.droppableId), destination.index);
  }
  async function createTask(input: TaskCreateInput) {
    await api.createTask(boardId!, input);
    await refresh();
    toast.success('Task created');
  }
  async function createWorkspace(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (modal === 'new-team') {
        const team = await api.createTeam({ name: name.trim() });
        setTeamSelection(team.id);
        setBoardSelection(null);
        setDirectBoard(null);
      } else {
        const created = await api.createBoard(teamId!, { name: name.trim(), visibility });
        setBoardSelection(created.id);
        setDirectBoard(null);
      }
      await client.invalidateQueries({ queryKey: prefix });
      setName('');
      setModal(null);
    } catch (e) {
      setError(api.errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function accept(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const team = await api.acceptInvitation(inviteToken.trim());
      setInviteToken('');
      onInviteAccepted();
      setTeamSelection(team.team_id);
      setBoardSelection(null);
      setDirectBoard(null);
      await client.invalidateQueries({ queryKey: prefix });
      setModal(null);
      toast.success('Invitation accepted');
    } catch (e) {
      setError(api.errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const tasks =
    state?.tasks.filter(
      (task) =>
        task.is_archived === archived &&
        (!search ||
          `${task.title} ${task.description || ''}`.toLowerCase().includes(search.toLowerCase())) &&
        (!label || task.labels.some((item) => item.id === Number(label))),
    ) || [];
  const allLabels = [
    ...new Map(
      state?.tasks.flatMap((task) => task.labels.map((item) => [item.id, item] as const)),
    ).values(),
  ];
  function openModal(value: typeof modal) {
    setModal(value);
    setError('');
    setName('');
  }
  function selectTeam(id: number) {
    setTeamSelection(id);
    setBoardSelection(null);
    setDirectBoard(null);
    setSelectedTask(null);
    setSearch('');
    setLabel('');
    setArchived(false);
  }
  return (
    <div className="app-container">
      <a className="skip-link" href="#board-main">
        Skip to board
      </a>
      <header className="nav-header">
        <a href="/" className="nav-brand">
          <span className="brand-mark" aria-hidden="true">
            ▥
          </span>
          TeamFlow
        </a>
        <div className="nav-controls">
          <label className="sr-only" htmlFor="select-team">
            Select team
          </label>
          <select
            id="select-team"
            className="nav-select"
            value={teamId || ''}
            onChange={(e) => selectTeam(Number(e.target.value))}
          >
            <option value="">Select team</option>
            {teams.data?.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </select>
          <label className="sr-only" htmlFor="select-board">
            Select board
          </label>
          <select
            id="select-board"
            className="nav-select"
            value={boardId || ''}
            onChange={(e) => {
              setBoardSelection(Number(e.target.value));
              setDirectBoard(null);
              setSelectedTask(null);
              setLabel('');
            }}
          >
            <option value="">Select board</option>
            {boards.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
            {directBoard && !boards.data?.some((item) => item.id === directBoard) ? (
              <option value={directBoard}>Shared board #{directBoard}</option>
            ) : null}
          </select>
          <div className="user-menu">
            <span className="avatar" aria-hidden="true">
              {user!.username[0].toUpperCase()}
            </span>
            <span>{user!.username}</span>
            <button className="logout-button" onClick={logout}>
              Log out
            </button>
          </div>
        </div>
      </header>
      <div className="workspace-toolbar">
        <div className="toolbar-group">
          <button onClick={() => openModal('new-team')}>+ New team</button>
          {selectedTeam && selectedTeam.role !== 'member' ? (
            <button onClick={() => openModal('new-board')}>+ New board</button>
          ) : null}
          {selectedTeam ? (
            <button onClick={() => openModal('team')}>Members & settings</button>
          ) : null}
        </div>
        <div className="toolbar-group">
          <button onClick={() => openModal('open-board')}>Open shared board</button>
          <button onClick={() => openModal('invite')}>Accept invitation</button>
        </div>
      </div>
      {inviteToken && modal !== 'invite' ? (
        <div className="notice">
          An invitation is ready for your account.{' '}
          <button onClick={() => openModal('invite')}>Review invitation</button>
        </div>
      ) : null}
      <main id="board-main" className="board-container">
        <div className="board-header">
          <div>
            <p className="eyebrow">
              {selectedTeam?.name || 'Shared workspace'}{' '}
              {selectedTeam ? `· ${selectedTeam.role}` : ''}
            </p>
            <h1>{state?.board.name || 'Your workspace'}</h1>
            <p className="muted">
              {state?.board.description || 'Plan together. Keep work moving.'}
            </p>
          </div>
          {state ? (
            <div className="board-actions">
              <span className={`connection ${connection === 'Live' ? 'live' : ''}`} role="status">
                {connection === 'Live' ? '●' : '○'} {connection}
              </span>
              <span className="role-tag">
                {canEdit ? 'Can edit' : 'Read only'} · {state.board.visibility}
              </span>
              <button onClick={() => openModal('activity')}>Activity</button>
              {canAdmin ? <button onClick={() => openModal('board')}>Board settings</button> : null}
            </div>
          ) : null}
        </div>
        {teams.isPending || (teamId && boards.isPending) || (boardId && board.isPending) ? (
          <div role="status" className="empty-state">
            Loading your workspace…
          </div>
        ) : null}
        {teams.error || boards.error || board.error ? (
          <div role="alert" className="error empty-state">
            {api.errorMessage(teams.error || boards.error || board.error)}
            <button onClick={() => void client.invalidateQueries({ queryKey: prefix })}>
              Try again
            </button>
          </div>
        ) : null}
        {!boardId && !teams.isPending && !boards.isPending ? (
          <div className="empty-state">
            <h2>{teamId ? 'Create your first board' : 'Start with a team'}</h2>
            <p>A shared space for tasks, conversations and clear ownership.</p>
            <button
              className="primary"
              onClick={() => openModal(teamId ? 'new-board' : 'new-team')}
              disabled={!!teamId && selectedTeam?.role === 'member'}
            >
              {teamId ? 'Create board' : 'Create team'}
            </button>
          </div>
        ) : null}
        {state ? (
          <>
            <div className="board-filters">
              <label htmlFor="task-search" className="sr-only">
                Search tasks
              </label>
              <input
                id="task-search"
                type="search"
                placeholder="Search tasks…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <label htmlFor="label-filter" className="sr-only">
                Filter by label
              </label>
              <select id="label-filter" value={label} onChange={(e) => setLabel(e.target.value)}>
                <option value="">All labels</option>
                {allLabels.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={archived}
                  onChange={(e) => setArchived(e.target.checked)}
                />
                Archived tasks
              </label>
              <span className="muted">
                {tasks.length} tasks · revision {state.revision}
              </span>
              {search || label ? (
                <span className="muted">Use card move controls while filtering.</span>
              ) : null}
            </div>
            <DragDropContext onDragEnd={onDragEnd}>
              <div className="board-columns" aria-label="Kanban columns">
                {[...state.columns]
                  .sort((a, b) => a.position - b.position)
                  .map((column) => (
                    <Column
                      key={column.id}
                      column={column}
                      tasks={tasks.filter((task) => task.column_id === column.id)}
                      columns={state.columns}
                      canEdit={canEdit}
                      canAdmin={canAdmin}
                      moving={movement.isPending}
                      dragDisabled={!!search || !!label || archived}
                      onOpen={setSelectedTask}
                      onMove={move}
                      onAdd={setAddTaskColumn}
                      onSettings={setColumnSettings}
                    />
                  ))}
                {canAdmin ? (
                  <button className="add-list-button" onClick={() => setColumnSettings('new')}>
                    + Add column
                  </button>
                ) : null}
              </div>
            </DragDropContext>
          </>
        ) : null}
      </main>
      {addTaskColumn !== null && state && canEdit ? (
        <NewTaskModal
          columnId={addTaskColumn}
          members={state.members}
          onClose={() => setAddTaskColumn(null)}
          onSubmit={createTask}
        />
      ) : null}
      {selectedTask && state?.tasks.find((task) => task.id === selectedTask) ? (
        <TaskDetailsModal
          key={selectedTask}
          task={state.tasks.find((task) => task.id === selectedTask)!}
          members={state.members}
          canEdit={canEdit}
          canAdmin={canAdmin}
          userId={userId}
          onClose={() => setSelectedTask(null)}
          onChange={refresh}
          onDeleted={() => setSelectedTask(null)}
        />
      ) : null}
      {columnSettings !== null && state && canAdmin ? (
        <ColumnSettings
          column={state.columns.find((column) => column.id === columnSettings)}
          columns={state.columns}
          revision={state.revision}
          boardId={state.board.id}
          onClose={() => setColumnSettings(null)}
          onChange={refresh}
        />
      ) : null}
      {modal === 'team' && selectedTeam ? (
        <TeamSettings
          key={selectedTeam.id}
          team={selectedTeam}
          userId={userId}
          onClose={() => setModal(null)}
          onDeleted={() => {
            setModal(null);
            setTeamSelection(null);
            setBoardSelection(null);
            setDirectBoard(null);
          }}
        />
      ) : null}
      {modal === 'board' && state && canAdmin ? (
        <BoardSettings
          state={state}
          team={teamDetails.data}
          onClose={() => setModal(null)}
          onChange={refresh}
          onDeleted={() => {
            setModal(null);
            setBoardSelection(null);
            setDirectBoard(null);
          }}
        />
      ) : null}
      {modal === 'activity' ? (
        <Modal title="Board activity" onClose={() => setModal(null)}>
          {activity.isPending ? (
            <p role="status">Loading activity…</p>
          ) : activity.error ? (
            <p role="alert" className="error">
              {api.errorMessage(activity.error)}
            </p>
          ) : (
            <ActivityPanel events={activity.data || []} />
          )}
        </Modal>
      ) : null}
      {modal === 'new-team' || modal === 'new-board' ? (
        <Modal
          title={modal === 'new-team' ? 'Create team' : 'Create board'}
          onClose={() => setModal(null)}
        >
          <form className="stack" onSubmit={createWorkspace}>
            <label htmlFor="workspace-name">
              {modal === 'new-team' ? 'Team name' : 'Board name'}
              <input
                id="workspace-name"
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={100}
              />
            </label>
            {modal === 'new-board' ? (
              <label htmlFor="new-visibility">
                Visibility
                <select
                  id="new-visibility"
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value as Visibility)}
                >
                  <option value="team">Team</option>
                  <option value="private">Private</option>
                  <option value="public-read">Public read</option>
                </select>
              </label>
            ) : null}
            {error ? (
              <p role="alert" className="error">
                {error}
              </p>
            ) : null}
            <div className="actions">
              <button type="button" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button className="primary" disabled={busy || !name.trim()}>
                Create
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
      {modal === 'open-board' ? (
        <Modal title="Open shared board" onClose={() => setModal(null)}>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              setDirectBoard(Number(boardNumber));
              setModal(null);
            }}
          >
            <p className="muted">
              Enter a board ID shared by a teammate. The server checks whether your account may view
              it.
            </p>
            <label htmlFor="board-id">
              Board ID
              <input
                id="board-id"
                type="number"
                min={1}
                value={boardNumber}
                onChange={(e) => setBoardNumber(e.target.value)}
                required
              />
            </label>
            <button className="primary">Open board</button>
          </form>
        </Modal>
      ) : null}
      {modal === 'invite' ? (
        <Modal title="Accept invitation" onClose={() => setModal(null)}>
          <form className="stack" onSubmit={accept}>
            <p>Signed in as {user!.email}. Invitations are bound to the invited account.</p>
            <label htmlFor="accept-token">
              Invitation token
              <input
                id="accept-token"
                autoFocus
                value={inviteToken}
                onChange={(e) => setInviteToken(e.target.value)}
                required
                autoComplete="off"
              />
            </label>
            {error ? (
              <p role="alert" className="error">
                {error}
              </p>
            ) : null}
            <button className="primary" disabled={busy || !inviteToken.trim()}>
              {busy ? 'Accepting…' : 'Accept invitation'}
            </button>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
