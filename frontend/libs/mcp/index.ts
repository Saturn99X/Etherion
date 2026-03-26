// Minimal MCP types to satisfy vendored Lobe app-types
// ARCH: Mirrors Lobe `src/libs/mcp/types.ts` error type union
export type MCPErrorType =
  | 'CONNECTION_FAILED'
  | 'PROCESS_SPAWN_ERROR'
  | 'INITIALIZATION_TIMEOUT'
  | 'VALIDATION_ERROR'
  | 'UNKNOWN_ERROR'
  | 'AUTHORIZATION_ERROR';
