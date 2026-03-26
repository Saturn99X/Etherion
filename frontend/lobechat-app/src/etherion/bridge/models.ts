import { useThreadPrefStore, type ThreadPreferences } from '@etherion/stores/thread-pref-store';

export type ThreadModelPreferences = ThreadPreferences;

/**
 * Return the current model/provider preferences for a thread/branch.
 */
export function getThreadModel(
  threadId: string,
  branchId?: string,
): ThreadModelPreferences {
  if (!threadId) {
    throw new Error('threadId is required to read thread model preferences');
  }

  return useThreadPrefStore.getState().getPrefs(threadId, branchId);
}

/**
 * Set the provider + model preference for a thread/branch.
 * This function does not validate that the provider/model pair is allowed;
 * that validation is the responsibility of Etherion backend + orchestration.
 */
export function setThreadModel(
  threadId: string,
  branchId: string | undefined,
  provider: string,
  model: string,
): void {
  if (!threadId) {
    throw new Error('threadId is required to set thread model preferences');
  }

  useThreadPrefStore
    .getState()
    .setPrefs(threadId, { provider, model }, branchId);
}

/**
 * List all provider IDs currently referenced in any thread preferences in
 * this client session. This reflects the set of providers actually used in
 * local thread state; a future backend metadata API can extend this.
 */
export function listAvailableProviders(): string[] {
  const state = useThreadPrefStore.getState();
  const providers = new Set<string>();

  for (const key of Object.keys(state.prefs)) {
    const pref = state.prefs[key];
    if (pref?.provider) {
      providers.add(pref.provider);
    }
  }

  return Array.from(providers);
}

/**
 * List all model IDs associated with a given provider across existing
 * thread preferences in this client session.
 */
export function listAvailableModels(providerId: string): string[] {
  const state = useThreadPrefStore.getState();
  const models = new Set<string>();

  for (const key of Object.keys(state.prefs)) {
    const pref = state.prefs[key];
    if (pref?.provider === providerId && pref.model) {
      models.add(pref.model);
    }
  }

  return Array.from(models);
}

/**
 * Clear any explicit model/provider preferences for a thread/branch.
 */
export function clearThreadModel(
  threadId: string,
  branchId?: string,
): void {
  if (!threadId) {
    return;
  }

  useThreadPrefStore.getState().clearPrefs(threadId, branchId);
}
