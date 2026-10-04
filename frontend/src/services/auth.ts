import { api } from './api';
import { LoginData, RegisterData, LoginResponse, User } from '../types/auth';

export const register = async (data: RegisterData): Promise<User> => {
  const response = await api.post('/auth/register', data, {
    headers: {
      'Content-Type': 'application/json',
    },
  });
  return response.data;
};

export const login = async (data: LoginData): Promise<LoginResponse> => {
  const formData = new URLSearchParams();
  formData.append('grant_type', 'password');
  formData.append('username', data.username);
  formData.append('password', data.password);

  const response = await api.post('/auth/login', formData.toString(), {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });
  return response.data;
};
