import { createContext, useContext } from 'react';
import type { User, LoginData, RegisterData } from '../types/auth';
export interface AuthState {
  user: User | null;
  login: (data: LoginData) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => void;
}
export const AuthContext = createContext<AuthState | undefined>(undefined);
export function useAuth() {
  const state = useContext(AuthContext);
  if (!state) throw new Error('useAuth must be used within an AuthProvider');
  return state;
}
