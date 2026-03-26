import { getClient } from '@etherion/lib/apollo-client';
import {
  GET_INTEGRATIONS_QUERY,
  CONNECT_INTEGRATION_MUTATION,
  TEST_INTEGRATION_MUTATION,
  DISCONNECT_INTEGRATION_MUTATION,
} from '@etherion/lib/graphql-operations';
import { useAuthStore } from '@etherion/stores/auth-store';
import { decodeJwt } from '@etherion/lib/jwt';

export interface Integration {
  serviceName: string;
  status: string;
  lastConnected?: string | null;
  errorMessage?: string | null;
  capabilities: string[];
}

export interface IntegrationConnectionResult {
  serviceName: string;
  status: string;
  validationErrors?: string[] | null;
}

export interface IntegrationTestResult {
  success: boolean;
  testResult?: string | null;
  errorMessage?: string | null;
}

interface GetIntegrationsResponse {
  getIntegrations: Integration[];
}

interface ConnectIntegrationResponse {
  connectIntegration: {
    serviceName: string;
    status: string;
    validationErrors?: string[] | null;
  };
}

interface TestIntegrationResponse {
  testIntegration: IntegrationTestResult;
}

function getTenantIdFromAuth(): number {
  const { token } = useAuthStore.getState();

  const rawToken =
    token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null);

  if (!rawToken) {
    throw new Error('Missing tenant identity: no auth token');
  }

  const payload = decodeJwt(rawToken);
  const tid = (payload && (payload.tenant_id ?? payload.tenantId)) as number | string | undefined;

  if (!tid) {
    throw new Error('Missing tenant identity in token');
  }

  const n = Number(tid);
  if (!Number.isFinite(n)) {
    throw new Error('Invalid tenant identity in token');
  }

  return n;
}

export async function listIntegrations(): Promise<Integration[]> {
  const tenantId = getTenantIdFromAuth();

  const { data } = await getClient().query<GetIntegrationsResponse>({
    query: GET_INTEGRATIONS_QUERY,
    variables: { tenant_id: tenantId },
    fetchPolicy: 'network-only',
  });

  return data?.getIntegrations ?? [];
}

export async function connectIntegration(
  serviceName: string,
  credentials: unknown,
): Promise<IntegrationConnectionResult> {
  if (!serviceName) {
    throw new Error('serviceName is required to connect an integration');
  }

  const serialized = JSON.stringify(credentials ?? {});

  const { data } = await getClient().mutate<ConnectIntegrationResponse>({
    mutation: CONNECT_INTEGRATION_MUTATION,
    variables: {
      service_name: serviceName,
      credentials: serialized,
    },
  });

  const payload = data?.connectIntegration;
  if (!payload) {
    throw new Error('Failed to connect integration');
  }

  return payload;
}

export async function testIntegration(serviceName: string): Promise<IntegrationTestResult> {
  if (!serviceName) {
    throw new Error('serviceName is required to test an integration');
  }

  const { data } = await getClient().mutate<TestIntegrationResponse>({
    mutation: TEST_INTEGRATION_MUTATION,
    variables: { service_name: serviceName },
  });

  const payload = data?.testIntegration;
  if (!payload) {
    throw new Error('Failed to test integration');
  }

  return payload;
}

export async function disconnectIntegration(serviceName: string): Promise<boolean> {
  if (!serviceName) {
    throw new Error('serviceName is required to disconnect an integration');
  }

  const { data } = await getClient().mutate<{ disconnectIntegration: boolean }>({
    mutation: DISCONNECT_INTEGRATION_MUTATION,
    variables: { service_name: serviceName },
  });

  return Boolean((data as any)?.disconnectIntegration);
}
