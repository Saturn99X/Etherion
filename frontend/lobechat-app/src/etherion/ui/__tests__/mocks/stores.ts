import { vi } from 'vitest';

// Mock Job Store
export const mockJobStore = {
  jobs: {
    'job-1': {
      id: 'job-1',
      status: 'RUNNING',
      progress: 50,
      stage: 'processing',
      substage: 'analyzing',
      goal: 'Test goal',
      createdAt: '2026-01-21T00:00:00Z',
    },
  },
  subscribeToJob: vi.fn(),
  unsubscribeFromJob: vi.fn(),
  updateJob: vi.fn(),
  getJob: vi.fn((jobId: string) => mockJobStore.jobs[jobId]),
};

// Mock Auth Store
export const mockAuthStore = {
  token: 'mock-jwt-token.eyJ0ZW5hbnRfaWQiOjF9.signature',
  user: {
    id: 'user-1',
    email: '<EMAIL>',
    name: 'Test User',
  },
  isAuthenticated: true,
  login: vi.fn(),
  logout: vi.fn(),
  setToken: vi.fn(),
};

// Mock Thread Store
export const mockThreadStore = {
  threads: {
    'thread-1': {
      id: 'thread-1',
      title: 'Test Thread',
      createdAt: '2026-01-21T00:00:00Z',
      messages: [],
    },
  },
  currentThreadId: 'thread-1',
  setCurrentThread: vi.fn(),
  addMessage: vi.fn(),
};

// Mock Thread Pref Store
export const mockThreadPrefStore = {
  preferences: {
    'thread-1': {
      modelProvider: 'openai',
      model: 'gpt-4',
      temperature: 0.7,
    },
  },
  getPreferences: vi.fn((threadId: string) => mockThreadPrefStore.preferences[threadId]),
  setPreferences: vi.fn(),
};

// Mock Team Store
export const mockTeamStore = {
  teams: [
    {
      id: 'team-1',
      name: 'Test Team',
      agents: ['agent-1', 'agent-2'],
    },
  ],
  currentTeam: null,
  setCurrentTeam: vi.fn(),
};

// Mock Toolcall Store
export const mockToolcallStore = {
  toolcalls: {},
  addToolcall: vi.fn(),
  updateToolcall: vi.fn(),
};

// Mock Chat Attachments Store
export const mockChatAttachmentsStore = {
  attachments: [],
  addAttachment: vi.fn(),
  removeAttachment: vi.fn(),
  clearAttachments: vi.fn(),
};

// Setup default store mocks
export const setupStoreMocks = () => {
  vi.mock('@etherion/stores/job-store', () => ({
    useJobStore: (selector?: any) => {
      if (typeof selector === 'function') {
        return selector(mockJobStore);
      }
      return mockJobStore;
    },
  }));

  vi.mock('@etherion/stores/auth-store', () => ({
    useAuthStore: (selector?: any) => {
      if (typeof selector === 'function') {
        return selector(mockAuthStore);
      }
      return mockAuthStore;
    },
  }));

  vi.mock('@etherion/stores/thread-store', () => ({
    useThreadStore: (selector?: any) => {
      if (typeof selector === 'function') {
        return selector(mockThreadStore);
      }
      return mockThreadStore;
    },
  }));

  vi.mock('@etherion/stores/thread-pref-store', () => ({
    useThreadPrefStore: (selector?: any) => {
      if (typeof selector === 'function') {
        return selector(mockThreadPrefStore);
      }
      return mockThreadPrefStore;
    },
  }));

  vi.mock('@etherion/stores/team-store', () => ({
    useTeamStore: (selector?: any) => {
      if (typeof selector === 'function') {
        return selector(mockTeamStore);
      }
      return mockTeamStore;
    },
  }));

  vi.mock('@etherion/stores/toolcall-store', () => ({
    useToolcallStore: (selector?: any) => {
      if (typeof selector === 'function') {
        return selector(mockToolcallStore);
      }
      return mockToolcallStore;
    },
  }));

  vi.mock('@etherion/stores/chat-attachments-store', () => ({
    useChatAttachmentsStore: (selector?: any) => {
      if (typeof selector === 'function') {
        return selector(mockChatAttachmentsStore);
      }
      return mockChatAttachmentsStore;
    },
  }));
};

// Reset all store mocks
export const resetStoreMocks = () => {
  mockJobStore.subscribeToJob.mockReset();
  mockJobStore.unsubscribeFromJob.mockReset();
  mockJobStore.updateJob.mockReset();
  mockAuthStore.login.mockReset();
  mockAuthStore.logout.mockReset();
  mockAuthStore.setToken.mockReset();
  mockThreadStore.setCurrentThread.mockReset();
  mockThreadStore.addMessage.mockReset();
  mockThreadPrefStore.setPreferences.mockReset();
  mockTeamStore.setCurrentTeam.mockReset();
  mockToolcallStore.addToolcall.mockReset();
  mockToolcallStore.updateToolcall.mockReset();
  mockChatAttachmentsStore.addAttachment.mockReset();
  mockChatAttachmentsStore.removeAttachment.mockReset();
  mockChatAttachmentsStore.clearAttachments.mockReset();
};
