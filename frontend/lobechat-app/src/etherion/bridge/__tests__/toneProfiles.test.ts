import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  applyToneProfileToGoal,
  applyToneProfileToThread,
  createToneProfile,
  deleteToneProfile,
  listToneProfiles,
  updateToneProfile,
  type ToneProfile,
} from '../toneProfiles';

const queryMock = vi.fn();
const mutateMock = vi.fn();

vi.mock('@etherion/lib/apollo-client', () => ({
  getClient: () => ({
    query: queryMock,
    mutate: mutateMock,
  }),
}));

const authState: any = {
  user: {
    user_id: '99',
  },
};

vi.mock('@etherion/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => authState,
  },
}));

beforeEach(() => {
  queryMock.mockReset();
  mutateMock.mockReset();
  authState.user = { user_id: '99' };
});

describe('etherion bridge: toneProfiles.ts - listToneProfiles', () => {
  it('listToneProfiles uses user_id from auth store when not provided', async () => {
    const profiles: ToneProfile[] = [
      {
        id: 'p1',
        name: 'Friendly',
        type: 'user',
        description: 'Friendly tone',
        usageCount: 10,
        lastUsed: '2024-01-01T00:00:00Z',
        effectiveness: 0.8,
      },
    ];

    queryMock.mockResolvedValueOnce({ data: { getToneProfiles: profiles } });

    const result = await listToneProfiles();

    expect(queryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { user_id: 99 },
      }),
    );
    expect(result).toEqual(profiles);
  });

  it('listToneProfiles respects explicit userId argument', async () => {
    queryMock.mockResolvedValueOnce({ data: { getToneProfiles: [] } });

    await listToneProfiles(42);

    expect(queryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { user_id: 42 },
      }),
    );
  });
});

describe('etherion bridge: toneProfiles.ts - mutations', () => {
  it('createToneProfile forwards profile_input and returns created core profile', async () => {
    const payload = {
      id: 'p2',
      name: 'Formal',
      type: 'user',
      description: 'Formal tone',
    };

    mutateMock.mockResolvedValueOnce({ data: { createToneProfile: payload } });

    const result = await createToneProfile({ name: 'Formal', type: 'user', description: 'Formal tone' });

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          profile_input: { name: 'Formal', type: 'user', description: 'Formal tone' },
        },
      }),
    );
    expect(result).toEqual(payload);
  });

  it('updateToneProfile forwards profile_id and profile_input and returns updated core profile', async () => {
    const payload = {
      id: 'p3',
      name: 'Casual',
      type: 'user',
      description: 'Casual tone',
    };

    mutateMock.mockResolvedValueOnce({ data: { updateToneProfile: payload } });

    const result = await updateToneProfile('p3', { name: 'Casual', description: 'Casual tone' });

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          profile_id: 'p3',
          profile_input: { name: 'Casual', description: 'Casual tone' },
        },
      }),
    );
    expect(result).toEqual(payload);
  });

  it('deleteToneProfile forwards profile_id and returns boolean result', async () => {
    mutateMock.mockResolvedValueOnce({ data: { deleteToneProfile: true } });

    const ok = await deleteToneProfile('p4');

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { profile_id: 'p4' },
      }),
    );
    expect(ok).toBe(true);
  });
});

describe('etherion bridge: toneProfiles.ts - apply', () => {
  it('applyToneProfileToGoal forwards profile_id and goal_id and returns boolean result', async () => {
    mutateMock.mockResolvedValueOnce({ data: { applyToneProfile: true } });

    const ok = await applyToneProfileToGoal('p5', 'goal-1');

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          profile_id: 'p5',
          goal_id: 'goal-1',
        },
      }),
    );
    expect(ok).toBe(true);
  });

  it('applyToneProfileToThread maps (threadId, profileId) onto applyToneProfileToGoal(profileId, threadId)', async () => {
    mutateMock.mockResolvedValueOnce({ data: { applyToneProfile: true } });

    const ok = await applyToneProfileToThread('thread-1', 'p6');

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          profile_id: 'p6',
          goal_id: 'thread-1',
        },
      }),
    );
    expect(ok).toBe(true);
  });
});
