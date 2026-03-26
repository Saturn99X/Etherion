import { getClient } from '@etherion/lib/apollo-client';
import {
  GET_AVAILABLE_MCP_TOOLS_QUERY,
  EXECUTE_MCP_TOOL_MUTATION,
  MANAGE_MCP_CREDENTIALS_MUTATION,
  TEST_MCP_TOOL_MUTATION,
} from '@etherion/lib/graphql-operations';

interface GetAvailableMcpToolsItem {
  name: string;
  description: string;
  category?: string | null;
  requiredCredentials?: string[] | null;
  capabilities?: string[] | null;
  status: string;
}

interface GetAvailableMcpToolsResponse {
  getAvailableMCPTools: GetAvailableMcpToolsItem[];
}

interface ExecuteMcpToolPayload {
  success: boolean;
  result?: string | null;
  executionTime?: number | null;
  errorMessage?: string | null;
  toolOutput?: string | null;
}

interface ExecuteMcpToolResponse {
  executeMCPTool: ExecuteMcpToolPayload;
}

interface ManageMcpCredentialsPayload {
  success: boolean;
  validationErrors?: string[] | null;
}

interface ManageMcpCredentialsResponse {
  manageMCPCredentials: ManageMcpCredentialsPayload;
}

interface TestMcpToolPayload {
  success: boolean;
  testResult?: string | null;
  errorMessage?: string | null;
}

interface TestMcpToolResponse {
  testMCPTool: TestMcpToolPayload;
}

export interface MCPTool {
  id: string;
  name: string;
  description: string;
  category: string;
  status: string;
  capabilities: string[];
  requiredCredentials: string[];
}

export interface ExecuteMcpToolResult extends ExecuteMcpToolPayload {}

export interface ManageCredentialsResult extends ManageMcpCredentialsPayload {}

export interface TestToolConnectionResult extends TestMcpToolPayload {}

export async function listTools(): Promise<MCPTool[]> {
  const { data } = await getClient().query<GetAvailableMcpToolsResponse>({
    query: GET_AVAILABLE_MCP_TOOLS_QUERY,
    fetchPolicy: 'network-only',
  });

  const items = data?.getAvailableMCPTools ?? [];

  return items.map((tool) => ({
    id: tool.name,
    name: tool.name,
    description: tool.description,
    category: tool.category ?? 'general',
    status: tool.status,
    capabilities: tool.capabilities ?? [],
    requiredCredentials: tool.requiredCredentials ?? [],
  }));
}

export async function getTool(toolId: string): Promise<MCPTool | null> {
  const id = (toolId ?? '').trim();
  if (!id) {
    throw new Error('toolId is required');
  }

  const tools = await listTools();
  return tools.find((t) => t.id === id) ?? null;
}

export async function listMcpPlugins(): Promise<MCPTool[]> {
  return listTools();
}

export async function executeTool(
  toolId: string,
  args: unknown,
): Promise<ExecuteMcpToolResult> {
  const id = (toolId ?? '').trim();
  if (!id) {
    throw new Error('toolId is required to execute a tool');
  }

  let params: string;
  try {
    params = JSON.stringify(args ?? {});
  } catch {
    throw new Error('Failed to serialize MCP tool params to JSON');
  }

  const { data } = await getClient().mutate<ExecuteMcpToolResponse>({
    mutation: EXECUTE_MCP_TOOL_MUTATION,
    variables: {
      tool_name: id,
      params,
    },
  });

  const payload = data?.executeMCPTool;
  if (!payload) {
    throw new Error('Failed to execute MCP tool');
  }

  return payload;
}

export async function setToolCredentials(
  toolId: string,
  credentials: unknown,
): Promise<ManageCredentialsResult> {
  const id = (toolId ?? '').trim();
  if (!id) {
    throw new Error('toolId is required to manage credentials');
  }

  let serialized: string;
  try {
    serialized = JSON.stringify(credentials ?? {});
  } catch {
    throw new Error('Failed to serialize MCP credentials to JSON');
  }

  const { data } = await getClient().mutate<ManageMcpCredentialsResponse>({
    mutation: MANAGE_MCP_CREDENTIALS_MUTATION,
    variables: {
      tool_name: id,
      credentials: serialized,
    },
  });

  const payload = data?.manageMCPCredentials;
  if (!payload) {
    throw new Error('Failed to manage MCP credentials');
  }

  return payload;
}

export async function testToolConnection(
  toolId: string,
): Promise<TestToolConnectionResult> {
  const id = (toolId ?? '').trim();
  if (!id) {
    throw new Error('toolId is required to test connection');
  }

  const { data } = await getClient().mutate<TestMcpToolResponse>({
    mutation: TEST_MCP_TOOL_MUTATION,
    variables: {
      tool_name: id,
    },
  });

  const payload = data?.testMCPTool;
  if (!payload) {
    throw new Error('Failed to test MCP tool');
  }

  return payload;
}
