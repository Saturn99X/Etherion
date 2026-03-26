/**
 * Reference-only: Mirrors LobeChat router contracts for MCP tools.
 * Not executed on FE. Kept for aligning types and capability taxonomy.
 */

export type MCPRegistryItem = {
  name: string;
  description?: string;
  category?: string;
  requiredCredentials?: string[];
  capabilities?: string[];
  status?: 'available' | 'disabled' | 'beta';
};

export interface MCPRegistryRef {
  list: () => Promise<MCPRegistryItem[]>;
  get: (name: string) => Promise<MCPRegistryItem | undefined>;
}

export const createMCPRegistryRef = (): MCPRegistryRef => ({
  async list() { return []; },
  async get() { return undefined; },
});
