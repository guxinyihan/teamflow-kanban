import { useEffect, useState } from 'react';
import { useQueryClient, type QueryKey } from '@tanstack/react-query';
import { api, getAccessToken, onSessionEnd } from '../services/api';
export function useBoardSocket(
  boardId: number | null,
  userId: number,
  boardKey: QueryKey,
  activityKey: QueryKey,
) {
  const client = useQueryClient();
  const [status, setStatus] = useState('Connecting');
  const boardKeyString = JSON.stringify(boardKey);
  const activityKeyString = JSON.stringify(activityKey);
  useEffect(() => {
    if (!boardId) return;
    let stopped = false;
    let attempts = 0;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      void client.invalidateQueries({ queryKey: JSON.parse(boardKeyString) });
      void client.invalidateQueries({ queryKey: JSON.parse(activityKeyString) });
    };
    function connect() {
      const token = getAccessToken();
      if (stopped || !token) return;
      const url = new URL(`${api.defaults.baseURL}/boards/${boardId}/ws`, window.location.origin);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(url);
      setStatus(attempts ? 'Reconnecting' : 'Connecting');
      socket.onopen = () => {
        if (!stopped) socket?.send(JSON.stringify({ token }));
      };
      socket.onmessage = (event) => {
        if (stopped) return;
        try {
          const message = JSON.parse(event.data);
          if (message.board_id !== boardId) return;
          if (message.type === 'ping') return;
          if (message.type === 'ready') {
            attempts = 0;
            setStatus('Live');
          }
          refresh();
          if (typeof message.type === 'string' && message.type.startsWith('board.'))
            void client.invalidateQueries({ queryKey: ['user', userId] });
        } catch {
          setStatus('Connection error');
        }
      };
      socket.onerror = () => {
        if (!stopped) setStatus('Connection interrupted');
      };
      socket.onclose = (event) => {
        if (stopped) return;
        if ([1008, 4401, 4403].includes(event.code)) {
          setStatus('Access ended');
          refresh();
          return;
        }
        setStatus('Reconnecting');
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 30000));
      };
    }
    function stop() {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
    }
    const unsubscribe = onSessionEnd(stop);
    connect();
    return () => {
      stop();
      unsubscribe();
    };
  }, [boardId, userId, client, boardKeyString, activityKeyString]);
  return status;
}
