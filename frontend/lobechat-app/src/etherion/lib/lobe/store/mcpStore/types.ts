/** Reference types adapted from LobeChat MCP store (minimal surface). */

export type MCPToolStatus = 'available' | 'disabled' | 'beta';

export interface MCPToolMeta {
  name: string;
  description?: string;
  category?: string;
  requiredCredentials?: string[];
  capabilities?: string[];
  status?: MCPToolStatus;
}

export interface MCPStoreState {
  tools: MCPToolMeta[];
  enabled: Record<string, boolean>;
}
