import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getUserSettings, updateUserSettings } from '../userSettings';

const queryMock = vi.fn();
const mutateMock = vi.fn();

vi.mock('@etherion/lib/apollo-client', () => ({
  getClient: () => ({
    query: queryMock,
    mutate: mutateMock,
  }),
}));

beforeEach(() => {
  queryMock.mockReset();
  mutateMock.mockReset();
});

describe('etherion bridge: userSettings.ts', () => {
  it('getUserSettings returns plain object from backend JSON', async () => {
    queryMock.mockResolvedValueOnce({
      data: { getUserSettings: { theme: 'dark', locale: 'en' } },
    });

    const settings = await getUserSettings();
    expect(queryMock).toHaveBeenCalledTimes(1);
    expect(settings).toEqual({ theme: 'dark', locale: 'en' });
  });

  it('getUserSettings normalizes non-object or null to {}', async () => {
    queryMock.mockResolvedValueOnce({ data: { getUserSettings: null } });
    expect(await getUserSettings()).toEqual({});

    queryMock.mockResolvedValueOnce({ data: { getUserSettings: 'str' } });
    expect(await getUserSettings()).toEqual({});

    queryMock.mockResolvedValueOnce({ data: { getUserSettings: ['x'] } });
    expect(await getUserSettings()).toEqual({});
  });

  it('updateUserSettings forwards patch and requires successful boolean response', async () => {
    mutateMock.mockResolvedValueOnce({ data: { updateUserSettings: true } });

    await updateUserSettings({ theme: 'light' });

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { settings: { theme: 'light' } },
      }),
    );
  });

  it('updateUserSettings throws when backend does not confirm success', async () => {
    mutateMock.mockResolvedValueOnce({ data: { updateUserSettings: false } });

    await expect(updateUserSettings({ theme: 'light' })).rejects.toThrow(
      'Failed to update user settings',
    );
  });

  it('updateUserSettings validates patch shape', async () => {
    // @ts-expect-error - runtime validation should reject non-object
    await expect(updateUserSettings(null)).rejects.toThrow(
      'updateUserSettings expects a plain object patch',
    );

    // @ts-expect-error - arrays are rejected
    await expect(updateUserSettings([])).rejects.toThrow(
      'updateUserSettings expects a plain object patch',
    );
  });
});
