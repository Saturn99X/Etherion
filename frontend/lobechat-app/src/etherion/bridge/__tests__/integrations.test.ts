import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  connectIntegration,
  disconnectIntegration,
  listIntegrations,
  testIntegration,
  type Integration,
} from '../integrations';
import * as jwt from '@etherion/lib/jwt';

const queryMock = vi.fn();
const mutateMock = vi.fn();

vi.mock('@etherion/lib/apollo-client', () => ({
  getClient: () => ({
    query: queryMock,
    mutate: mutateMock,
  }),
}));

const authState: any = {
  token: 'jwt-token',
};

vi.mock('@etherion/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => authState,
  },
}));

vi.mock('@etherion/lib/jwt', () => ({
  decodeJwt: vi.fn(),
}));

const jwtMock = vi.mocked(jwt);

beforeEach(() => {
  queryMock.mockReset();
  mutateMock.mockReset();
  jwtMock.decodeJwt.mockReset();
  authState.token = 'jwt-token';
});

describe('etherion bridge: integrations.ts - listIntegrations', () => {
  it('listIntegrations derives tenant_id from JWT and forwards to GET_INTEGRATIONS_QUERY', async () => {
    const integrations: Integration[] = [
      {
        serviceName: 'openai',
        status: 'connected',
        lastConnected: '2024-01-01T00:00:00Z',
        errorMessage: null,
        capabilities: ['completion'],
      },
    ];

    jwtMock.decodeJwt.mockReturnValueOnce({ tenant_id: 456 } as any);
    queryMock.mockResolvedValueOnce({ data: { getIntegrations: integrations } });

    const result = await listIntegrations();

    expect(jwtMock.decodeJwt).toHaveBeenCalledWith('jwt-token');
    expect(queryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { tenant_id: 456 },
      }),
    );
    expect(result).toEqual(integrations);
  });
});

describe('etherion bridge: integrations.ts - mutations', () => {
  it('connectIntegration validates serviceName and forwards JSON credentials', async () => {
    const payload = {
      serviceName: 'openai',
      status: 'connected',
      validationErrors: null,
    };

    mutateMock.mockResolvedValueOnce({ data: { connectIntegration: payload } });

    const creds = { api_key: 'k', region: 'us' };
    const result = await connectIntegration('openai', creds);

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          service_name: 'openai',
          credentials: JSON.stringify(creds),
        },
      }),
    );
    expect(result).toEqual(payload);
  });

  it('connectIntegration throws when serviceName is empty', async () => {
    // @ts-expect-error runtime validation
    await expect(connectIntegration('', {})).rejects.toThrow(
      'serviceName is required to connect an integration',
    );
  });

  it('testIntegration forwards service_name and returns payload', async () => {
    const payload = {
      success: true,
      testResult: 'ok',
      errorMessage: null,
    };

    mutateMock.mockResolvedValueOnce({ data: { testIntegration: payload } });

    const result = await testIntegration('openai');

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { service_name: 'openai' },
      }),
    );
    expect(result).toEqual(payload);
  });

  it('disconnectIntegration forwards service_name and returns boolean result', async () => {
    mutateMock.mockResolvedValueOnce({ data: { disconnectIntegration: true } });

    const ok = await disconnectIntegration('openai');

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { service_name: 'openai' },
      }),
    );
    expect(ok).toBe(true);
  });
});
