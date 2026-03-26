import { MockedResponse } from '@apollo/client/testing';
import {
  GET_AGENTS_QUERY,
  GET_JOB_HISTORY_QUERY,
  GET_JOB_DETAILS_QUERY,
  CREATE_AGENT_MUTATION,
  UPDATE_AGENT_MUTATION,
  DELETE_AGENT_MUTATION,
  LIST_AGENT_TEAMS_QUERY,
  CREATE_AGENT_TEAM_MUTATION,
  UPDATE_AGENT_TEAM_MUTATION,
  GET_INTEGRATIONS_QUERY,
  CONNECT_INTEGRATION_MUTATION,
  TEST_INTEGRATION_MUTATION,
  LIST_REPOSITORY_ASSETS,
  GET_AVAILABLE_MCP_TOOLS_QUERY,
  EXECUTE_MCP_TOOL_MUTATION,
  TEST_MCP_TOOL_MUTATION,
  GET_PROJECTS_QUERY,
  CREATE_PROJECT_MUTATION,
  UPDATE_PROJECT_MUTATION,
  DELETE_PROJECT_MUTATION,
} from '@etherion/lib/graphql-operations';

// Default Apollo mocks for common queries
export const defaultApolloMocks: MockedResponse[] = [
  // Agents
  {
    request: {
      query: GET_AGENTS_QUERY,
      variables: { tenant_id: 1 },
    },
    result: {
      data: {
        getAgents: [
          {
            id: 'agent-1',
            name: 'Test Agent',
            description: 'A test agent for unit testing',
            agentType: 'general',
            capabilities: ['coding', 'testing', 'debugging'],
            status: 'active',
            createdAt: '2026-01-21T00:00:00Z',
            lastUsed: '2026-01-21T12:00:00Z',
            performanceMetrics: {
              successRate: 0.95,
              averageExecutionTime: 12.5,
              totalExecutions: 100,
            },
          },
          {
            id: 'agent-2',
            name: 'Research Agent',
            description: 'An agent for research tasks',
            agentType: 'research',
            capabilities: ['research', 'analysis'],
            status: 'active',
            createdAt: '2026-01-20T00:00:00Z',
          },
        ],
      },
    },
  },

  // Job History
  {
    request: {
      query: GET_JOB_HISTORY_QUERY,
      variables: { limit: 10, offset: 0, status: null },
    },
    result: {
      data: {
        getJobHistory: {
          jobs: [
            {
              id: 'job-1',
              goal: 'Test goal execution',
              status: 'COMPLETED',
              createdAt: '2026-01-21T00:00:00Z',
              completedAt: '2026-01-21T00:05:00Z',
              duration: '5m 0s',
              totalCost: '$0.05',
              modelUsed: 'gpt-4',
              threadId: 'thread-1',
            },
            {
              id: 'job-2',
              goal: 'Another test goal',
              status: 'RUNNING',
              createdAt: '2026-01-21T00:10:00Z',
              duration: '2m 30s',
              totalCost: '$0.02',
              modelUsed: 'gpt-4',
              threadId: 'thread-2',
            },
          ],
          totalCount: 2,
        },
      },
    },
  },

  // Agent Teams
  {
    request: {
      query: LIST_AGENT_TEAMS_QUERY,
    },
    result: {
      data: {
        listAgentTeams: [
          {
            id: 'team-1',
            name: 'Development Team',
            description: 'Team for software development',
            agents: ['agent-1', 'agent-2'],
            createdAt: '2026-01-21T00:00:00Z',
          },
        ],
      },
    },
  },

  // Integrations
  {
    request: {
      query: GET_INTEGRATIONS_QUERY,
    },
    result: {
      data: {
        getIntegrations: [
          {
            id: 'integration-1',
            name: 'GitHub',
            type: 'github',
            status: 'connected',
            connectedAt: '2026-01-21T00:00:00Z',
          },
          {
            id: 'integration-2',
            name: 'Slack',
            type: 'slack',
            status: 'disconnected',
          },
        ],
      },
    },
  },

  // Repository Assets
  {
    request: {
      query: LIST_REPOSITORY_ASSETS,
    },
    result: {
      data: {
        listRepositoryAssets: [
          {
            id: 'asset-1',
            filename: 'output.txt',
            mimeType: 'text/plain',
            sizeBytes: 512,
            createdAt: '2026-01-21T00:00:00Z',
            downloadUrl: 'https://example.com/download/output.txt',
            jobId: 'job-1',
          },
        ],
      },
    },
  },

  // MCP Tools
  {
    request: {
      query: GET_AVAILABLE_MCP_TOOLS_QUERY,
    },
    result: {
      data: {
        getAvailableMcpTools: [
          {
            id: 'tool-1',
            name: 'file_reader',
            description: 'Read files from the filesystem',
            category: 'filesystem',
            status: 'available',
            schema: {
              type: 'object',
              properties: {
                path: { type: 'string' },
              },
              required: ['path'],
            },
          },
        ],
      },
    },
  },

  // Projects
  {
    request: {
      query: GET_PROJECTS_QUERY,
    },
    result: {
      data: {
        getProjects: [
          {
            id: 'project-1',
            name: 'Test Project',
            description: 'A test project',
            createdAt: '2026-01-21T00:00:00Z',
            updatedAt: '2026-01-21T00:00:00Z',
          },
        ],
      },
    },
  },
];

// Helper to create custom Apollo mocks
export const createApolloMocks = (customMocks: MockedResponse[] = []): MockedResponse[] => {
  return [...defaultApolloMocks, ...customMocks];
};

// Helper to create error mocks
export const createErrorMock = (query: any, variables: any, errorMessage: string): MockedResponse => {
  return {
    request: {
      query,
      variables,
    },
    error: new Error(errorMessage),
  };
};

// Helper to create loading mock (never resolves)
export const createLoadingMock = (query: any, variables: any): MockedResponse => {
  return {
    request: {
      query,
      variables,
    },
    result: {
      data: {},
    },
    delay: Infinity,
  };
};
