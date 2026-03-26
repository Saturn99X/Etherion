import { AuthService, PasswordAuthService, type GoogleLoginResult } from '@etherion/lib/services/auth-service';
import { useAuthStore } from '@etherion/stores/auth-store';

export { getGoogleOAuthUrl, getGithubOAuthUrl } from '@etherion/lib/services/auth-service';

function withAuthLoading<T>(operation: () => Promise<T>): Promise<T> {
  const store = useAuthStore.getState();
  store.setLoading(true);
  store.setError(null);

  return operation()
    .catch((error) => {
      const message = error instanceof Error ? error.message : 'Authentication error';
      useAuthStore.getState().setError(message);
      throw error;
    })
    .finally(() => {
      useAuthStore.getState().setLoading(false);
    });
}

/**
 * UI-facing Auth bridge for LobeChat.
 *
 * This module exposes a thin set of functions that wrap Etherion's
 * AuthService / PasswordAuthService and auth store. LobeChat UI components
 * should depend on these functions instead of calling GraphQL or stores
 * directly.
 */

export async function loginWithGoogle(
  code: string,
  inviteToken?: string,
): Promise<GoogleLoginResult> {
  return withAuthLoading(() => AuthService.googleLogin(code, inviteToken));
}

export async function loginWithGithub(code: string, inviteToken?: string) {
  return withAuthLoading(() => AuthService.githubLogin(code, inviteToken));
}

export async function loginWithPassword(
  email: string,
  password: string,
  inviteToken?: string,
) {
  return withAuthLoading(() =>
    PasswordAuthService.login(email, password, inviteToken),
  );
}

export async function signupWithPassword(
  email: string,
  password: string,
  name?: string,
  inviteToken?: string,
  subdomain?: string,
) {
  return withAuthLoading(() =>
    PasswordAuthService.signup(email, password, name, inviteToken, subdomain),
  );
}

export async function logout(): Promise<boolean> {
  return withAuthLoading(() => AuthService.logout());
}

/**
 * Initialize auth state from any persisted token, if present.
 *
 * This should typically be called once on app bootstrap.
 */
export async function initializeAuth(): Promise<void> {
  await withAuthLoading(() => AuthService.initializeAuth());
}

export async function refreshAuth(): Promise<boolean> {
  return withAuthLoading(() => AuthService.refreshAuth());
}

/**
 * Fetch the current user from the backend and return the raw GraphQL shape.
 * Bridges UI code to the Etherion getCurrentUser query.
 */
export type CurrentUser = Awaited<ReturnType<typeof AuthService.getCurrentUser>>;
export type AuthStateSnapshot = ReturnType<typeof useAuthStore.getState>;
export type AuthUser = AuthStateSnapshot['user'];

export async function getCurrentUser(): Promise<CurrentUser> {
  return AuthService.getCurrentUser();
}

/**
 * Convenience helpers to read the current auth store snapshot.
 */
export function getAuthState(): AuthStateSnapshot {
  return useAuthStore.getState();
}

export function isAuthenticated(): boolean {
  return useAuthStore.getState().isAuthenticated;
}
