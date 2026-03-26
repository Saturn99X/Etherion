import { getClient } from '@etherion/lib/apollo-client';
import {
  GET_AGENTS_QUERY,
  CREATE_AGENT_MUTATION,
  UPDATE_AGENT_MUTATION,
  DELETE_AGENT_MUTATION,
  EXECUTE_AGENT_MUTATION,
  LIST_AGENT_TEAMS_QUERY,
  CREATE_AGENT_TEAM_MUTATION,
  UPDATE_AGENT_TEAM_MUTATION,
} from '@etherion/lib/graphql-operations';
import { useAuthStore } from '@etherion/stores/auth-store';
import { decodeJwt } from '@etherion/lib/jwt';

interface AgentPerformanceMetrics {
  successRate?: number;
  averageExecutionTime?: number;
  totalExecutions?: number;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  lastUsed?: string | null;
  status: string;
  agentType: string;
  capabilities: string[];
  performanceMetrics?: AgentPerformanceMetrics | null;
}

export interface AgentInput {
  name: string;
  description: string;
  agentType: string;
  capabilities: string[];
  systemPrompt?: string;
}

interface GetAgentsResponse {
  getAgents: Agent[];
}

export interface AgentMutationResult {
  id: string;
  name: string;
  description: string;
  status: string;
}

interface CreateAgentResponse {
  createAgent: AgentMutationResult;
}

interface UpdateAgentResponse {
  updateAgent: AgentMutationResult;
}

interface ExecuteAgentPayload {
  success: boolean;
  result?: string | null;
  executionTime?: number | null;
  cost?: number | null;
}

interface ExecuteAgentResponse {
  executeAgent: ExecuteAgentPayload;
}

export interface ExecuteAgentResult extends ExecuteAgentPayload {}

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

export async function listAgents(): Promise<Agent[]> {
  const tenantId = getTenantIdFromAuth();

  const { data } = await getClient().query<GetAgentsResponse>({
    query: GET_AGENTS_QUERY,
    variables: { tenant_id: tenantId },
    fetchPolicy: 'network-only',
  });

  return data?.getAgents ?? [];
}

export async function createAgent(input: AgentInput): Promise<AgentMutationResult> {
  const { data } = await getClient().mutate<CreateAgentResponse>({
    mutation: CREATE_AGENT_MUTATION,
    variables: { agent_input: input },
  });

  const created = data?.createAgent;
  if (!created) {
    throw new Error('Failed to create agent');
  }

  return created;
}

export async function updateAgent(agentId: string, input: AgentInput): Promise<AgentMutationResult> {
  if (!agentId) {
    throw new Error('agentId is required to update an agent');
  }

  const { data } = await getClient().mutate<UpdateAgentResponse>({
    mutation: UPDATE_AGENT_MUTATION,
    variables: { agent_id: agentId, agent_input: input },
  });

  const updated = data?.updateAgent;
  if (!updated) {
    throw new Error('Failed to update agent');
  }

  return updated;
}

export async function deleteAgent(agentId: string): Promise<boolean> {
  if (!agentId) {
    throw new Error('agentId is required to delete an agent');
  }

  const { data } = await getClient().mutate<{ deleteAgent: boolean }>({
    mutation: DELETE_AGENT_MUTATION,
    variables: { agent_id: agentId },
  });

  return Boolean((data as any)?.deleteAgent);
}

export async function executeAgent(
  agentId: string,
  payload: unknown,
): Promise<ExecuteAgentResult> {
  if (!agentId) {
    throw new Error('agentId is required to execute an agent');
  }

  const input = JSON.stringify(payload ?? {});

  const { data } = await getClient().mutate<ExecuteAgentResponse>({
    mutation: EXECUTE_AGENT_MUTATION,
    variables: { agent_id: agentId, input },
  });

  const result = data?.executeAgent;
  if (!result) {
    throw new Error('Failed to execute agent');
  }

  return result;
}

// ---------------------------------------------------------------------------
// Agent Teams
// ---------------------------------------------------------------------------

export interface AgentTeam {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  lastUpdatedAt: string;
  isActive: boolean;
  isSystemTeam: boolean;
  version: number;
  customAgentIDs: string[];
  preApprovedToolNames: string[];
}

export interface AgentTeamInput {
  name: string;
  description?: string;
  customAgentIDs?: string[];
  preApprovedToolNames?: string[];
}

interface ListAgentTeamsResponse {
  listAgentTeams: AgentTeam[];
}

interface CreateAgentTeamResponse {
  createAgentTeam: AgentTeam;
}

export async function listAgentTeams(
  limit?: number,
  offset?: number,
): Promise<AgentTeam[]> {
  const { data } = await getClient().query<ListAgentTeamsResponse>({
    query: LIST_AGENT_TEAMS_QUERY,
    variables: {
      limit: limit ?? 50,
      offset: offset ?? 0,
    },
    fetchPolicy: 'network-only',
  });

  return data?.listAgentTeams ?? [];
}

export async function createAgentTeam(input: AgentTeamInput): Promise<AgentTeam> {
  const { data } = await getClient().mutate<CreateAgentTeamResponse>({
    mutation: CREATE_AGENT_TEAM_MUTATION,
    variables: {
      team_input: {
        name: input.name,
        description: input.description ?? '',
        customAgentIDs: input.customAgentIDs ?? [],
        preApprovedToolNames: input.preApprovedToolNames ?? [],
      },
    },
  });

  const created = data?.createAgentTeam;
  if (!created) {
    throw new Error('Failed to create agent team');
  }

  return created;
}

export async function updateAgentTeam(
  agentTeamId: string,
  patch: Partial<Pick<AgentTeamInput, 'name' | 'description' | 'preApprovedToolNames'>>,
): Promise<boolean> {
  if (!agentTeamId) {
    throw new Error('agentTeamId is required to update an agent team');
  }

  const { name, description, preApprovedToolNames } = patch;

  const { data } = await getClient().mutate<{ updateAgentTeam: boolean }>({
    mutation: UPDATE_AGENT_TEAM_MUTATION,
    variables: {
      agent_team_id: agentTeamId,
      name,
      description,
      pre_approved_tool_names: preApprovedToolNames,
    },
  });

  return Boolean((data as any)?.updateAgentTeam);
}
