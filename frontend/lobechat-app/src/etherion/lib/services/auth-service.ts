import { getClient } from '@etherion/lib/apollo-client';
import { useAuthStore } from '@etherion/stores/auth-store';
import {
  GOOGLE_LOGIN_MUTATION,
  GITHUB_LOGIN_MUTATION,
  PASSWORD_SIGNUP_MUTATION,
  PASSWORD_LOGIN_MUTATION,
  GET_CURRENT_USER_QUERY,
  LOGOUT_MUTATION
} from '@etherion/lib/graphql-operations';

/**
 * Safely resolve environment variable with validation and fallbacks.
 * Prioritizes runtime window.ENV (Cloud Run), falls back to build-time process.env.
 * 
 * @param key - Environment variable name
 * @param required - If true, throws error when variable is not found
 * @returns The resolved environment variable value or undefined
 * @throws Error if required is true and variable is not set
 */
function getEnvVar(key: string, required: boolean = false): string | undefined {
  let value: string | undefined;

  // Priority 1: Runtime window.ENV (Cloud Run injected)
  if (typeof window !== 'undefined' && (window as any).ENV) {
    value = (window as any).ENV[key];
  }

  // Priority 2: Build-time process.env
  if (!value && typeof process !== 'undefined' && process.env) {
    value = process.env[key];
  }

  // Normalize empty strings to undefined
  value = value?.trim() || undefined;

  if (required && !value) {
    throw new Error(`Required environment variable ${key} is not configured`);
  }

  return value;
}

interface GoogleLoginResponse {
  googleLogin: {
    access_token: string;
    token_type: string;
    user: {
      user_id: string;
      email: string;
      name: string;
      provider: string;
      profile_picture_url?: string;
      tenant_subdomain?: string | null;
    };
  };
}

export const getGithubOAuthUrl = (): string => {
  const clientId = getEnvVar('NEXT_PUBLIC_GITHUB_CLIENT_ID', true)!;
  let callback = getEnvVar('NEXT_PUBLIC_AUTH_CALLBACK_URL');

  // Fallback to current origin if env not set
  if (!callback && typeof window !== 'undefined') {
    callback = `${window.location.origin}/auth/callback`;
  }

  if (!callback) {
    throw new Error('Auth callback URL not configured and cannot be inferred');
  }

  const redirectUri = encodeURIComponent(callback);
  // Encode provider + optional invite token into OAuth state to avoid cross-provider mixups
  let stateParam = '';
  try {
    const inv = typeof window !== 'undefined' ? window.localStorage.getItem('invite_token') : null;
    const stateObj = { p: 'github', inv: inv || undefined } as { p: 'github'; inv?: string };
    const s = typeof btoa !== 'undefined' ? btoa(JSON.stringify(stateObj)) : Buffer.from(JSON.stringify(stateObj)).toString('base64');
    stateParam = `&state=${encodeURIComponent(s)}`;
  } catch (_) { }
  const scope = encodeURIComponent('read:user user:email');
  return `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&scope=${scope}${stateParam}`;
};

export class PasswordAuthService {
  static async signup(
    email: string,
    password: string,
    name?: string,
    invite_token?: string,
    subdomain?: string,
  ) {
    const { data } = await getClient().mutate<any>({
      mutation: PASSWORD_SIGNUP_MUTATION,
      variables: { email, password, name, invite_token, subdomain },
    });
    const res = data?.passwordSignup;
    if (!res) throw new Error('Signup failed');
    localStorage.setItem('auth_token', res.access_token);
    useAuthStore.getState().login(res.access_token, res.user);
    return res;
  }
  static async login(email: string, password: string, invite_token?: string) {
    const { data } = await getClient().mutate<any>({
      mutation: PASSWORD_LOGIN_MUTATION,
      variables: { email, password, invite_token },
    });
    const res = data?.passwordLogin;
    if (!res) throw new Error('Login failed');
    localStorage.setItem('auth_token', res.access_token);
    useAuthStore.getState().login(res.access_token, res.user);
    return res;
  }
}


interface CurrentUserResponse {
  getCurrentUser: {
    user_id: string;
    created_at: string;
  } | null;
}

interface LogoutResponse {
  logout: boolean;
}

export interface GoogleLoginResult {
  access_token: string;
  token_type: string;
  user: {
    user_id: string;
    email: string;
    name: string;
    provider: string;
    profile_picture_url?: string;
    tenant_subdomain?: string | null;
  };
}

export class AuthService {
  static async googleLogin(code: string, invite_token?: string) {
    try {
      let callback =
        (typeof window !== 'undefined'
          ? (window as any).ENV?.NEXT_PUBLIC_AUTH_CALLBACK_URL
          : process.env.NEXT_PUBLIC_AUTH_CALLBACK_URL) || '';
      if (!callback && typeof window !== 'undefined') {
        callback = `${window.location.origin}/auth/callback`;
      }
      const redirect_uri = callback;
      const { data } = await getClient().mutate<GoogleLoginResponse>({
        mutation: GOOGLE_LOGIN_MUTATION,
        variables: { code, invite_token, redirect_uri },
      });

      if (!data?.googleLogin) {
        throw new Error('Login failed - no response data');
      }

      const { access_token, token_type, user } = data.googleLogin;
      localStorage.setItem('auth_token', access_token);
      useAuthStore.getState().login(access_token, user);
      return { access_token, token_type, user } as GoogleLoginResult;
    } catch (error) {
      console.error('Google login error:', error);
      useAuthStore.getState().setError(error instanceof Error ? error.message : 'Login failed');
      throw error;
    }
  }

  static async githubLogin(code: string, invite_token?: string) {
    try {
      let callback =
        (typeof window !== 'undefined'
          ? (window as any).ENV?.NEXT_PUBLIC_AUTH_CALLBACK_URL
          : process.env.NEXT_PUBLIC_AUTH_CALLBACK_URL) || '';
      if (!callback && typeof window !== 'undefined') {
        callback = `${window.location.origin}/auth/callback`;
      }
      const redirect_uri = callback;
      const { data } = await getClient().mutate<any>({
        mutation: GITHUB_LOGIN_MUTATION,
        variables: { code, invite_token, redirect_uri },
      });
      const res = data?.githubLogin;
      if (!res) throw new Error('Login failed - no response data');
      localStorage.setItem('auth_token', res.access_token);
      useAuthStore.getState().login(res.access_token, res.user);
      return res;
    } catch (error) {
      useAuthStore.getState().setError(error instanceof Error ? error.message : 'Login failed');
      throw error;
    }
  }

  static async getCurrentUser() {
    try {
      const { data } = await getClient().query<CurrentUserResponse>({
        query: GET_CURRENT_USER_QUERY,
        fetchPolicy: 'network-only', // Always fetch fresh data
      });

      return data?.getCurrentUser || null;
    } catch (error) {
      console.error('Get current user error:', error);
      return null;
    }
  }

  static async logout(): Promise<boolean> {
    try {
      const token = useAuthStore.getState().token;
      if (!token) {
        // Already logged out
        useAuthStore.getState().logout();
        return true;
      }

      const { data } = await getClient().mutate<LogoutResponse>({
        mutation: LOGOUT_MUTATION,
        variables: { token },
      });

      // Clear auth state regardless of server response
      useAuthStore.getState().logout();

      return data?.logout === true;
    } catch (error) {
      console.error('Logout error:', error);
      // Still clear local state even if server logout fails
      useAuthStore.getState().logout();
      return true;
    }
  }

  static async refreshAuth(): Promise<boolean> {
    try {
      const currentUser = await this.getCurrentUser();
      if (currentUser) {
        // User is still authenticated
        return true;
      } else {
        // User is not authenticated anymore
        useAuthStore.getState().logout();
        return false;
      }
    } catch (error) {
      console.error('Refresh auth error:', error);
      useAuthStore.getState().logout();
      return false;
    }
  }

  static async initializeAuth(): Promise<void> {
    const token = localStorage.getItem('auth_token');
    const authStore = useAuthStore.getState();

    if (token && !authStore.isAuthenticated) {
      // Try to get current user to validate the token
      const currentUser = await this.getCurrentUser();
      if (currentUser) {
        // Token is valid, restore auth state
        authStore.login(token, {
          user_id: currentUser.user_id,
          email: '', // We don't have email from getCurrentUser
          name: '',  // We don't have name from getCurrentUser
          provider: 'google',
        });
      } else {
        // Token is invalid, clear it
        localStorage.removeItem('auth_token');
      }
    }
  }
}

// OAuth redirect URL helper
export const getGoogleOAuthUrl = (): string => {
  // Validate BEFORE building URL - this will throw if not configured
  const clientId = getEnvVar('NEXT_PUBLIC_GOOGLE_CLIENT_ID', true)!;
  let callback = getEnvVar('NEXT_PUBLIC_AUTH_CALLBACK_URL');

  // Fallback callback to current origin
  if (!callback && typeof window !== 'undefined') {
    callback = `${window.location.origin}/auth/callback`;
  }

  if (!callback) {
    throw new Error('Auth callback URL not configured and cannot be inferred');
  }

  const redirectUri = encodeURIComponent(callback);
  // Encode provider + optional invite token into OAuth state to avoid cross-provider mixups
  let stateParam = '';
  try {
    const inv = typeof window !== 'undefined' ? window.localStorage.getItem('invite_token') : null;
    const stateObj = { p: 'google', inv: inv || undefined } as { p: 'google'; inv?: string };
    const s = typeof btoa !== 'undefined' ? btoa(JSON.stringify(stateObj)) : Buffer.from(JSON.stringify(stateObj)).toString('base64');
    stateParam = `&state=${encodeURIComponent(s)}`;
  } catch (_) { }

  return (
    `https://accounts.google.com/o/oauth2/v2/auth?` +
    `client_id=${clientId}&` +
    `redirect_uri=${redirectUri}&` +
    `response_type=code&` +
    `scope=email profile&` +
    `access_type=offline&` +
    `prompt=consent` +
    stateParam
  );
};
