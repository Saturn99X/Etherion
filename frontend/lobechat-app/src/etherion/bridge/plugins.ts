import type { ExecuteMcpToolResult, MCPTool } from './mcp';
import { executeTool, listTools } from './mcp';

export interface ChatPlugin {
  id: string;
  toolName: string;
  name: string;
  description: string;
  category: string;
  capabilities: string[];
}

export async function listChatPlugins(): Promise<ChatPlugin[]> {
  const tools: MCPTool[] = await listTools();

  const byId = new Map<string, ChatPlugin>();

  for (const tool of tools) {
    const id = tool.id;
    if (!id) continue;

    const plugin: ChatPlugin = {
      id,
      toolName: id,
      name: tool.name,
      description: tool.description,
      category: tool.category,
      capabilities: tool.capabilities,
    };

    byId.set(id, plugin);
  }

  const plugins = Array.from(byId.values());
  plugins.sort((a, b) => a.name.localeCompare(b.name));

  return plugins;
}

export async function invokePlugin(
  pluginId: string,
  payload: unknown,
): Promise<ExecuteMcpToolResult> {
  const id = (pluginId ?? '').trim();
  if (!id) {
    throw new Error('pluginId is required to invoke a plugin');
  }

  return executeTool(id, payload);
}
