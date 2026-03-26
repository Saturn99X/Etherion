import { getClient } from '@etherion/lib/apollo-client';
import {
  GET_TONE_PROFILES_QUERY,
  CREATE_TONE_PROFILE_MUTATION,
  UPDATE_TONE_PROFILE_MUTATION,
  DELETE_TONE_PROFILE_MUTATION,
  APPLY_TONE_PROFILE_MUTATION,
} from '@etherion/lib/graphql-operations';
import { useAuthStore } from '@etherion/stores/auth-store';

export interface ToneProfile {
  id: string;
  name: string;
  type: string;
  description: string;
  usageCount: number;
  lastUsed?: string | null;
  effectiveness?: number | null;
}

export interface ToneProfileInput {
  name: string;
  type?: string;
  description?: string;
}

interface GetToneProfilesResponse {
  getToneProfiles: ToneProfile[];
}

interface ToneProfileCore {
  id: string;
  name: string;
  type: string;
  description: string;
}

interface CreateToneProfileResponse {
  createToneProfile: ToneProfileCore;
}

interface UpdateToneProfileResponse {
  updateToneProfile: ToneProfileCore;
}

function getUserIdFromAuth(): number {
  const { user } = useAuthStore.getState();

  if (!user || !user.user_id) {
    throw new Error('Missing user identity for tone profiles');
  }

  const n = Number(user.user_id);
  if (!Number.isFinite(n)) {
    throw new Error('Invalid user identity in auth store');
  }

  return n;
}

export async function listToneProfiles(userId?: number): Promise<ToneProfile[]> {
  const resolvedUserId = userId ?? getUserIdFromAuth();

  const { data } = await getClient().query<GetToneProfilesResponse>({
    query: GET_TONE_PROFILES_QUERY,
    variables: { user_id: resolvedUserId },
    fetchPolicy: 'network-only',
  });

  return data?.getToneProfiles ?? [];
}

export async function createToneProfile(input: ToneProfileInput): Promise<ToneProfileCore> {
  const { data } = await getClient().mutate<CreateToneProfileResponse>({
    mutation: CREATE_TONE_PROFILE_MUTATION,
    variables: { profile_input: input },
  });

  const created = data?.createToneProfile;
  if (!created) {
    throw new Error('Failed to create tone profile');
  }

  return created;
}

export async function updateToneProfile(
  profileId: string,
  input: ToneProfileInput,
): Promise<ToneProfileCore> {
  if (!profileId) {
    throw new Error('profileId is required to update a tone profile');
  }

  const { data } = await getClient().mutate<UpdateToneProfileResponse>({
    mutation: UPDATE_TONE_PROFILE_MUTATION,
    variables: {
      profile_id: profileId,
      profile_input: input,
    },
  });

  const updated = data?.updateToneProfile;
  if (!updated) {
    throw new Error('Failed to update tone profile');
  }

  return updated;
}

export async function deleteToneProfile(profileId: string): Promise<boolean> {
  if (!profileId) {
    throw new Error('profileId is required to delete a tone profile');
  }

  const { data } = await getClient().mutate<{ deleteToneProfile: boolean }>({
    mutation: DELETE_TONE_PROFILE_MUTATION,
    variables: { profile_id: profileId },
  });

  return Boolean((data as any)?.deleteToneProfile);
}

export async function applyToneProfileToGoal(
  profileId: string,
  goalId: string,
): Promise<boolean> {
  if (!profileId) {
    throw new Error('profileId is required to apply a tone profile');
  }

  if (!goalId) {
    throw new Error('goalId is required to apply a tone profile');
  }

  const { data } = await getClient().mutate<{ applyToneProfile: boolean }>({
    mutation: APPLY_TONE_PROFILE_MUTATION,
    variables: {
      profile_id: profileId,
      goal_id: goalId,
    },
  });

  return Boolean((data as any)?.applyToneProfile);
}

export async function applyToneProfileToThread(
  threadId: string,
  profileId: string,
): Promise<boolean> {
  return applyToneProfileToGoal(profileId, threadId);
}
