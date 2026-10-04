import { useEffect, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { User, LoginData, RegisterData } from '../types/auth';
import { AuthContext } from './authState';
import { endSession, onSessionEnd, setAccessToken } from '../services/api';
import * as authService from '../services/auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const client = useQueryClient();
  useEffect(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('kanban_columns');
    sessionStorage.removeItem('user');
    return onSessionEnd(() => {
      void client.cancelQueries();
      client.clear();
      setUser(null);
    });
  }, [client]);
  async function login(data: LoginData) {
    const response = await authService.login(data);
    await client.cancelQueries();
    client.clear();
    setAccessToken(response.access_token);
    setUser(response.user);
  }
  async function register(data: RegisterData) {
    await authService.register(data);
    await login({ username: data.username, password: data.password });
  }
  return (
    <AuthContext.Provider value={{ user, login, register, logout: endSession }}>
      {children}
    </AuthContext.Provider>
  );
}
