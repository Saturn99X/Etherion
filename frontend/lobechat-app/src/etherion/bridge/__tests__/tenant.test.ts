import { beforeEach, describe, expect, it, vi } from 'vitest';

import { updateTenantSubdomain } from '../tenant';

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

describe('etherion bridge: tenant.ts', () => {
  it('updateTenantSubdomain enforces non-empty subdomain', async () => {
    await expect(updateTenantSubdomain('')).rejects.toThrow(
      'Subdomain must not be empty',
    );
    await expect(updateTenantSubdomain('   ')).rejects.toThrow(
      'Subdomain must not be empty',
    );
  });

  it('updateTenantSubdomain trims and lowercases input and returns result', async () => {
    mutateMock.mockResolvedValueOnce({
      data: {
        updateTenantSubdomain: {
          id: 1,
          tenantId: 'tnt_123',
          subdomain: 'newsub',
          name: 'Acme',
          adminEmail: '<EMAIL>',
          createdAt: '2025-01-01T00:00:00Z',
          inviteToken: null,
          success: true,
          message: 'ok',
        },
      },
    });

    const result = await updateTenantSubdomain(' NewSub ');

    expect(mutateMock).toHaveBeenCalledTimes(1);
    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { new_subdomain: 'newsub' },
      }),
    );

    expect(result.subdomain).toBe('newsub');
    expect(result.success).toBe(true);
  });

  it('updateTenantSubdomain throws when backend returns null', async () => {
    mutateMock.mockResolvedValueOnce({
      data: {
        updateTenantSubdomain: null,
      },
    });

    await expect(updateTenantSubdomain('valid')).rejects.toThrow(
      'Failed to update tenant subdomain',
    );
  });

  it('updateTenantSubdomain throws when success is false and surfaces message', async () => {
    mutateMock.mockResolvedValueOnce({
      data: {
        updateTenantSubdomain: {
          id: 1,
          tenantId: 'tnt_123',
          subdomain: 'taken',
          name: 'Acme',
          adminEmail: '<EMAIL>',
          createdAt: '2025-01-01T00:00:00Z',
          inviteToken: null,
          success: false,
          message: 'Subdomain already taken',
        },
      },
    });

    await expect(updateTenantSubdomain('taken')).rejects.toThrow(
      'Subdomain already taken',
    );
  });
});
