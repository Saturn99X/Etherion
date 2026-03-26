import { beforeEach, describe, expect, it, vi } from 'vitest';

const authState = {
  user: null as any,
  token: null as string | null,
  isAuthenticated: false,
  isLoading: false,
  error: null as string | null,
  login: () => {},
  logout: () => {},
  updateUser: () => {},
  setLoading: (isLoading: boolean) => {
    authState.isLoading = isLoading;
  },
  setError: (error: string | null) => {
    authState.error = error;
  },
};

vi.mock('@etherion/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => authState,
    setState: (partial: Partial<typeof authState>) => {
      Object.assign(authState, partial);
    },
  },
}));

import {
  loginWithGoogle,
  loginWithGithub,
  loginWithPassword,
  signupWithPassword,
  logout,
  initializeAuth,
  refreshAuth,
  getCurrentUser,
} from '../auth';
import {
  AuthService,
  PasswordAuthService,
  type GoogleLoginResult,
} from '@etherion/lib/services/auth-service';

vi.mock('@etherion/lib/services/auth-service', () => ({
  AuthService: {
    googleLogin: vi.fn(),
    githubLogin: vi.fn(),
    logout: vi.fn(),
    refreshAuth: vi.fn(),
    initializeAuth: vi.fn(),
    getCurrentUser: vi.fn(),
  },
  PasswordAuthService: {
    login: vi.fn(),
    signup: vi.fn(),
  },
  getGoogleOAuthUrl: vi.fn(() => 'https://auth.example/google'),
  getGithubOAuthUrl: vi.fn(() => 'https://auth.example/github'),
}));

const mockedAuthService = vi.mocked(AuthService, true);
const mockedPasswordAuthService = vi.mocked(PasswordAuthService, true);

const initialAuthSnapshot = { ...authState };

beforeEach(() => {
  Object.assign(authState, initialAuthSnapshot, {
    isAuthenticated: false,
    isLoading: false,
    error: null,
  });
  vi.clearAllMocks();
});

describe('etherion bridge: auth.ts', () => {
  it('loginWithGoogle forwards to AuthService and drives loading state', async () => {
    const result: GoogleLoginResult = {
      access_token: 'tok',
      token_type: 'bearer',
      user: {
        user_id: 'u1',
        email: '<EMAIL>',
        name: 'User',
        provider: 'google',
        profile_picture_url: undefined,
      },
    };
    mockedAuthService.googleLogin.mockResolvedValueOnce(result);

    const promise = loginWithGoogle('code123', 'inv1');
    expect(authState.isLoading).toBe(true);

    const value = await promise;
    expect(mockedAuthService.googleLogin).toHaveBeenCalledWith('code123', 'inv1');
    expect(value).toEqual(result);
    expect(authState.isLoading).toBe(false);
    expect(authState.error).toBeNull();
  });

  it('loginWithGoogle sets error and rethrows on failure', async () => {
    mockedAuthService.googleLogin.mockRejectedValueOnce(new Error('boom'));

    await expect(loginWithGoogle('code123')).rejects.toThrow('boom');
    expect(authState.isLoading).toBe(false);
    expect(authState.error).toBe('boom');
  });

  it('loginWithGithub delegates to AuthService.githubLogin', async () => {
    mockedAuthService.githubLogin.mockResolvedValueOnce({ ok: true });

    const res = await loginWithGithub('code456', 'inv2');
    expect(mockedAuthService.githubLogin).toHaveBeenCalledWith('code456', 'inv2');
    expect(res).toEqual({ ok: true });
  });

  it('loginWithPassword delegates to PasswordAuthService.login', async () => {
    mockedPasswordAuthService.login.mockResolvedValueOnce({ token: 't' });

    const res = await loginWithPassword('<EMAIL>', 'pw', 'inv3');
    expect(mockedPasswordAuthService.login).toHaveBeenCalledWith(
      '<EMAIL>',
      'pw',
      'inv3',
    );
    expect(res).toEqual({ token: 't' });
  });

  it('signupWithPassword delegates to PasswordAuthService.signup', async () => {
    mockedPasswordAuthService.signup.mockResolvedValueOnce({ token: 't2' });

    const res = await signupWithPassword('<EMAIL>', 'pw2', 'User 2', 'inv4', 'acme');
    expect(mockedPasswordAuthService.signup).toHaveBeenCalledWith(
      '<EMAIL>',
      'pw2',
      'User 2',
      'inv4',
      'acme',
    );
    expect(res).toEqual({ token: 't2' });
  });

  it('logout delegates to AuthService.logout', async () => {
    mockedAuthService.logout.mockResolvedValueOnce(true);

    const res = await logout();
    expect(mockedAuthService.logout).toHaveBeenCalledTimes(1);
    expect(res).toBe(true);
  });

  it('initializeAuth delegates to AuthService.initializeAuth', async () => {
    mockedAuthService.initializeAuth.mockResolvedValueOnce();

    await initializeAuth();
    expect(mockedAuthService.initializeAuth).toHaveBeenCalledTimes(1);
  });

  it('refreshAuth delegates to AuthService.refreshAuth', async () => {
    mockedAuthService.refreshAuth.mockResolvedValueOnce(true);

    const res = await refreshAuth();
    expect(mockedAuthService.refreshAuth).toHaveBeenCalledTimes(1);
    expect(res).toBe(true);
  });

  it('getCurrentUser delegates to AuthService.getCurrentUser', async () => {
    mockedAuthService.getCurrentUser.mockResolvedValueOnce({ id: 1, user_id: 'u1' });

    const res = await getCurrentUser();
    expect(mockedAuthService.getCurrentUser).toHaveBeenCalledTimes(1);
    expect(res).toEqual({ id: 1, user_id: 'u1' });
  });
});
