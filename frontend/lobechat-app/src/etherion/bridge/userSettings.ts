import { getClient } from '@etherion/lib/apollo-client';
import {
  GET_USER_SETTINGS_QUERY,
  UPDATE_USER_SETTINGS_MUTATION,
} from '@etherion/lib/graphql-operations';

export type UserSettings = Record<string, unknown>;

interface GetUserSettingsResponse {
  getUserSettings: UserSettings | null;
}

interface UpdateUserSettingsResponse {
  updateUserSettings: boolean | null;
}

/**
 * Fetch the current user's settings as an opaque JSON object.
 * The bridge does not interpret individual keys; it only enforces that
 * the result is a plain object.
 */
export async function getUserSettings(): Promise<UserSettings> {
  const { data } = await getClient().query<GetUserSettingsResponse>({
    query: GET_USER_SETTINGS_QUERY,
    fetchPolicy: 'network-only',
  });

  const raw = data?.getUserSettings;

  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {};
  }

  return raw;
}

/**
 * Apply a partial settings patch on the backend.
 *
 * The backend is responsible for merging this JSON patch with existing
 * settings; this bridge only validates that a plain object is provided
 * and forwards it to the GraphQL mutation.
 */
export async function updateUserSettings(
  patch: Partial<UserSettings>,
): Promise<void> {
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) {
    throw new Error('updateUserSettings expects a plain object patch');
  }

  const { data } = await getClient().mutate<UpdateUserSettingsResponse>({
    mutation: UPDATE_USER_SETTINGS_MUTATION,
    variables: {
      settings: patch,
    },
  });

  if (!data || data.updateUserSettings !== true) {
    throw new Error('Failed to update user settings');
  }
}
