import { getClient } from '@etherion/lib/apollo-client';
import { HEALTH_CHECK_QUERY } from '@etherion/lib/graphql-operations';

interface HealthCheckResponse {
  health_check: string;
}

export interface HealthStatus {
  ok: boolean;
  message: string;
}

/**
 * Bridge 17 – Health
 *
 * Thin wrapper over Etherion's GraphQL health_check field.
 * LobeChat UI should depend on this instead of calling GraphQL directly.
 */
export async function checkHealth(): Promise<HealthStatus> {
  try {
    const { data } = await getClient().query<HealthCheckResponse>({
      query: HEALTH_CHECK_QUERY,
      fetchPolicy: 'network-only',
    });

    if (!data || typeof data.health_check !== 'string') {
      return {
        ok: false,
        message: 'Invalid health_check response',
      };
    }

    return {
      ok: true,
      message: data.health_check,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Health check failed';
    return {
      ok: false,
      message,
    };
  }
}
