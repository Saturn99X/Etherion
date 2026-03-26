/**
 * Reference-only mirror of LobeChat server MCP service surface.
 * Not executed in FE. Used to keep contracts close for future GraphQL wiring.
 */

export type MCPCapability = 'test' | 'execute' | 'discover';

export interface MCPService {
  listManifests: () => Promise<string[]>; // urls or ids
  getCapabilities: (toolName: string) => Promise<MCPCapability[]>;
}

export const createMCPServiceRef = (): MCPService => ({
  async listManifests() { return []; },
  async getCapabilities() { return ['test','execute']; },
});
