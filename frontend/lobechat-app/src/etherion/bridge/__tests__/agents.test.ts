import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  deleteAgent,
  executeAgent,
  listAgentTeams,
  listAgents,
  createAgent,
  updateAgent,
  createAgentTeam,
  updateAgentTeam,
  type Agent,
  type AgentTeam,
} from '../agents';
import * as jwt from '@etherion/lib/jwt';

const queryMock = vi.fn();
const mutateMock = vi.fn();

vi.mock('@etherion/lib/apollo-client', () => ({
  getClient: () => ({
    query: queryMock,
    mutate: mutateMock,
  }),
}));

const authState: any = {
  token: 'jwt-token',
};

vi.mock('@etherion/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => authState,
  },
}));

vi.mock('@etherion/lib/jwt', () => ({
  decodeJwt: vi.fn(),
}));

const jwtMock = vi.mocked(jwt);

beforeEach(() => {
  queryMock.mockReset();
  mutateMock.mockReset();
  jwtMock.decodeJwt.mockReset();
  authState.token = 'jwt-token';
});

describe('etherion bridge: agents.ts - listAgents', () => {
  it('listAgents derives tenant_id from JWT and forwards to GET_AGENTS_QUERY', async () => {
    const agents: Agent[] = [
      {
        id: 'a1',
        name: 'Agent 1',
        description: 'desc',
        createdAt: '2024-01-01T00:00:00Z',
        lastUsed: null,
        status: 'active',
        agentType: 'custom',
        capabilities: ['x'],
        performanceMetrics: null,
      },
    ];

    jwtMock.decodeJwt.mockReturnValueOnce({ tenant_id: 123 } as any);
    queryMock.mockResolvedValueOnce({ data: { getAgents: agents } });

    const result = await listAgents();

    expect(jwtMock.decodeJwt).toHaveBeenCalledWith('jwt-token');
    expect(queryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { tenant_id: 123 },
      }),
    );
    expect(result).toEqual(agents);
  });

  it('listAgents throws when tenant identity is missing in token', async () => {
    jwtMock.decodeJwt.mockReturnValueOnce({} as any);

    await expect(listAgents()).rejects.toThrow('Missing tenant identity in token');
    expect(queryMock).not.toHaveBeenCalled();
  });
});

describe('etherion bridge: agents.ts - mutations', () => {
  it('createAgent forwards AgentInput and returns mutation payload', async () => {
    const payload = {
      id: 'a2',
      name: 'Agent 2',
      description: 'd2',
      status: 'inactive',
    };

    mutateMock.mockResolvedValueOnce({ data: { createAgent: payload } });

    const result = await createAgent({
      name: 'Agent 2',
      description: 'd2',
      agentType: 'custom',
      capabilities: ['c1', 'c2'],
      systemPrompt: 'prompt',
    });

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          agent_input: {
            name: 'Agent 2',
            description: 'd2',
            agentType: 'custom',
            capabilities: ['c1', 'c2'],
            systemPrompt: 'prompt',
          },
        },
      }),
    );
    expect(result).toEqual(payload);
  });

  it('updateAgent requires agentId and returns mutation payload', async () => {
    const payload = {
      id: 'a3',
      name: 'Agent 3',
      description: 'd3',
      status: 'active',
    };

    mutateMock.mockResolvedValueOnce({ data: { updateAgent: payload } });

    const result = await updateAgent('a3', {
      name: 'Agent 3',
      description: 'd3',
      agentType: 'custom',
      capabilities: [],
    });

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          agent_id: 'a3',
          agent_input: {
            name: 'Agent 3',
            description: 'd3',
            agentType: 'custom',
            capabilities: [],
          },
        },
      }),
    );
    expect(result).toEqual(payload);
  });

  it('deleteAgent forwards agent_id and returns boolean result', async () => {
    mutateMock.mockResolvedValueOnce({ data: { deleteAgent: true } });

    const result = await deleteAgent('a4');

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { agent_id: 'a4' },
      }),
    );
    expect(result).toBe(true);
  });

  it('executeAgent serializes payload as JSON string and returns execution payload', async () => {
    const execPayload = {
      success: true,
      result: 'ok',
      executionTime: 1.23,
      cost: 0.5,
    };

    mutateMock.mockResolvedValueOnce({ data: { executeAgent: execPayload } });

    const payload = { input: 'hello' };
    const result = await executeAgent('a5', payload);

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          agent_id: 'a5',
          input: JSON.stringify(payload),
        },
      }),
    );
    expect(result).toEqual(execPayload);
  });
});

describe('etherion bridge: agents.ts - teams', () => {
  it('listAgentTeams forwards pagination and returns list', async () => {
    const teams: AgentTeam[] = [
      {
        id: 't1',
        name: 'Team 1',
        description: 'desc',
        createdAt: '2024-01-01T00:00:00Z',
        lastUpdatedAt: '2024-01-02T00:00:00Z',
        isActive: true,
        isSystemTeam: false,
        version: 1,
        customAgentIDs: ['a1'],
        preApprovedToolNames: ['tool1'],
      },
    ];

    queryMock.mockResolvedValueOnce({ data: { listAgentTeams: teams } });

    const result = await listAgentTeams(10, 5);

    expect(queryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: { limit: 10, offset: 5 },
      }),
    );
    expect(result).toEqual(teams);
  });

  it('createAgentTeam injects defaults for optional arrays and returns created team', async () => {
    const team: AgentTeam = {
      id: 't2',
      name: 'Team 2',
      description: 'desc2',
      createdAt: '2024-01-03T00:00:00Z',
      lastUpdatedAt: '2024-01-03T00:00:00Z',
      isActive: true,
      isSystemTeam: false,
      version: 1,
      customAgentIDs: [],
      preApprovedToolNames: [],
    };

    mutateMock.mockResolvedValueOnce({ data: { createAgentTeam: team } });

    const result = await createAgentTeam({ name: 'Team 2', description: 'desc2' });

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          team_input: {
            name: 'Team 2',
            description: 'desc2',
            customAgentIDs: [],
            preApprovedToolNames: [],
          },
        },
      }),
    );
    expect(result).toEqual(team);
  });

  it('updateAgentTeam forwards partial fields and returns boolean result', async () => {
    mutateMock.mockResolvedValueOnce({ data: { updateAgentTeam: true } });

    const ok = await updateAgentTeam('t3', {
      name: 'Team 3',
      description: 'd3',
      preApprovedToolNames: ['toolA'],
    });

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variables: {
          agent_team_id: 't3',
          name: 'Team 3',
          description: 'd3',
          pre_approved_tool_names: ['toolA'],
        },
      }),
    );
    expect(ok).toBe(true);
  });
});
