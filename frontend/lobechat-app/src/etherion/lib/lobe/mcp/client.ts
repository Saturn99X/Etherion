/**
 * Reference-only MCP client interfaces mirrored from LobeChat patterns.
 * ARCH: Keep Etherion-UI agnostic; bridge via GraphQL in Step 4/6.
 */

export type MCPManifest = { name: string; version?: string; tools?: string[] };
export type MCPToolParams = Record<string, unknown>;

export interface MCPClient {
  /** Load a tool manifest (reference contract). */
  loadManifest: (manifestUrl: string) => Promise<MCPManifest>;
  /** Test a tool is callable in current tenant/context. */
  testTool: (toolName: string) => Promise<{ success: boolean; message?: string }>; 
  /** Execute a tool with params (bridge to GraphQL in Etherion). */
  executeTool: (
    toolName: string,
    params: MCPToolParams
  ) => Promise<{ success: boolean; result?: unknown; errorMessage?: string }>;
}

// TODO: Replace with real implementation wired to Etherion GraphQL mutations in Step 4/6
export const createMCPClient = (): MCPClient => ({
  async loadManifest() {
    // WHY: placeholder to satisfy imports until GraphQL bridge is wired
    return { name: 'mcp', tools: [] };
  },
  async testTool() {
    return { success: true };
  },
  async executeTool() {
    return { success: false, errorMessage: 'Not implemented in FE stub' };
  },
});
