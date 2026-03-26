import { getClient } from '@etherion/lib/apollo-client';
import { UPDATE_TENANT_SUBDOMAIN_MUTATION } from '@etherion/lib/graphql-operations';

export interface Tenant {
  id: number;
  tenantId: string;
  subdomain: string;
  name: string;
  adminEmail: string;
  createdAt: string;
}

export interface TenantUpdateResult extends Tenant {
  success?: boolean | null;
  message?: string | null;
}

interface UpdateTenantSubdomainResponse {
  updateTenantSubdomain: TenantUpdateResult | null;
}

/**
 * Bridge 18 – Tenant & Domain
 *
 * Provides a thin wrapper around the updateTenantSubdomain GraphQL mutation.
 * UI code should use this bridge instead of calling GraphQL directly.
 */
export async function updateTenantSubdomain(newSubdomain: string): Promise<TenantUpdateResult> {
  const trimmed = newSubdomain.trim().toLowerCase();
  if (!trimmed) {
    throw new Error('Subdomain must not be empty');
  }

  const { data } = await getClient().mutate<UpdateTenantSubdomainResponse>({
    mutation: UPDATE_TENANT_SUBDOMAIN_MUTATION,
    variables: { new_subdomain: trimmed },
  });

  const result = data?.updateTenantSubdomain;
  if (!result) {
    throw new Error('Failed to update tenant subdomain');
  }

  if (result.success === false) {
    throw new Error(result.message || 'Tenant subdomain update failed');
  }

  return result;
}
