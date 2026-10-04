import { beforeEach, describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';
import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { api, endSession, getAccessToken, onSessionEnd, setAccessToken } from '../services/api';

beforeEach(endSession);

function unauthorized(config: InternalAxiosRequestConfig) {
  return new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, {
    config,
    status: 401,
    statusText: 'Unauthorized',
    headers: {},
    data: {},
  });
}

describe('responses from an earlier authenticated session', () => {
  it('does not let an old request log out a newly signed-in account', async () => {
    let rejectOld: ((error: AxiosError) => void) | undefined;
    let oldConfig: InternalAxiosRequestConfig | undefined;
    setAccessToken('old-account-token');
    const pending = api.get('/boards/1/state', {
      adapter: (config) =>
        new Promise((_resolve, reject) => {
          oldConfig = config;
          rejectOld = reject;
        }),
    });
    await waitFor(() => expect(oldConfig).toBeDefined());
    expect(oldConfig!.headers.get('Authorization')).toBe('Bearer old-account-token');
    endSession();
    setAccessToken('new-account-token');
    const sessionEnded = vi.fn();
    const unsubscribe = onSessionEnd(sessionEnded);
    const rejected = expect(pending).rejects.toBeInstanceOf(AxiosError);
    rejectOld!(unauthorized(oldConfig!));
    await rejected;
    expect(getAccessToken()).toBe('new-account-token');
    expect(sessionEnded).not.toHaveBeenCalled();
    unsubscribe();
  });

  it('still ends the current session when its own request returns 401', async () => {
    setAccessToken('current-account-token');
    const sessionEnded = vi.fn();
    const unsubscribe = onSessionEnd(sessionEnded);
    await expect(
      api.get('/boards/1/state', {
        adapter: async (config) => {
          throw unauthorized(config);
        },
      }),
    ).rejects.toBeInstanceOf(AxiosError);
    expect(getAccessToken()).toBeNull();
    expect(sessionEnded).toHaveBeenCalledOnce();
    unsubscribe();
  });
});
