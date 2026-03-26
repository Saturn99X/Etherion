import { create } from 'zustand';
import { nanoid } from 'nanoid';

// NOTE: Minimal client-side contracts aligned with Z/lobechat-integration-roadmap.md Step 2.
// These are UI-only scaffolds; persistence/GraphQL wiring will follow in later steps.

export type Artifact = { kind: 'html' | 'svg' | 'doc' | 'code'; content: string; title?: string };

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  parentId?: string; // message tree linkage
  branchId?: string; // branch grouping
  timestamp: string;
  metadata?: {
    cot?: string; // summarized reasoning steps (not raw long CoT)
    artifacts?: Artifact[]; // rendered in Artifacts panel
    toolExecId?: string; // link to MCP execution (Step 4)
    // UI-local flags (not persisted server-side)
    showCot?: boolean;
    showArtifacts?: boolean;
  };
};

export interface ThreadStoreState {
  // Messages grouped by threadId
  threads: Record<string, ChatMessage[]>;

  // Add or append a message to a thread
  addMessage: (threadId: string, message: ChatMessage) => void;

  // Create a new branch at a given message id and return the new branchId
  createBranch: (threadId: string, atMessageId: string) => string;

  // Selector helpers
  getMessagesByBranch: (threadId: string, branchId?: string) => ChatMessage[];

  // UI toggles for a specific message in a thread
  toggleCot: (threadId: string, messageId: string) => void;
  toggleArtifacts: (threadId: string, messageId: string) => void;

  // Updates for streaming / post-run enrichment
  updateMessageContent: (threadId: string, messageId: string, content: string) => void;
  setMessageMetadata: (
    threadId: string,
    messageId: string,
    metadata: Partial<NonNullable<ChatMessage['metadata']>>,
  ) => void;
}

export const useThreadStore = create<ThreadStoreState>((set, get) => ({
  threads: {},

  addMessage: (threadId, message) =>
    set((state) => {
      const list = state.threads[threadId] ?? [];
      return {
        threads: {
          ...state.threads,
          [threadId]: [...list, message],
        },
      };
    }),

  createBranch: (threadId, atMessageId) => {
    const state = get();
    const messages = state.threads[threadId] ?? [];
    const forkMsg = messages.find((m) => m.id === atMessageId);
    const newBranchId = nanoid();

    // Duplicate context up to the fork point and mark the new branch on a copy of the fork
    const forkIndex = forkMsg ? messages.indexOf(forkMsg) : -1;
    const baseContext = forkIndex >= 0 ? messages.slice(0, forkIndex + 1) : messages;

    const branchedContext: ChatMessage[] = baseContext.map((m) =>
      m.id === atMessageId ? { ...m, branchId: newBranchId } : { ...m }
    );

    set((prev) => ({
      threads: {
        ...prev.threads,
        [threadId]: branchedContext,
      },
    }));

    return newBranchId;
  },

  getMessagesByBranch: (threadId, branchId) => {
    const messages = get().threads[threadId] ?? [];
    if (!branchId) return messages;
    return messages.filter((m) => m.branchId === branchId);
  },

  toggleCot: (threadId, messageId) =>
    set((state) => {
      const list = state.threads[threadId] ?? [];
      const updated = list.map((m) =>
        m.id === messageId
          ? {
              ...m,
              metadata: {
                ...m.metadata,
                showCot: !m.metadata?.showCot,
              },
            }
          : m
      );
      return { threads: { ...state.threads, [threadId]: updated } };
    }),

  toggleArtifacts: (threadId, messageId) =>
    set((state) => {
      const list = state.threads[threadId] ?? [];
      const updated = list.map((m) =>
        m.id === messageId
          ? {
              ...m,
              metadata: {
                ...m.metadata,
                showArtifacts: !m.metadata?.showArtifacts,
              },
            }
          : m
      );
      return { threads: { ...state.threads, [threadId]: updated } };
    }),

  updateMessageContent: (threadId, messageId, content) =>
    set((state) => {
      const list = state.threads[threadId] ?? [];
      const updated = list.map((m) => (m.id === messageId ? { ...m, content } : m));
      return { threads: { ...state.threads, [threadId]: updated } };
    }),

  setMessageMetadata: (threadId, messageId, metadata) =>
    set((state) => {
      const list = state.threads[threadId] ?? [];
      const updated = list.map((m) =>
        m.id === messageId
          ? {
              ...m,
              metadata: {
                ...m.metadata,
                ...metadata,
              },
            }
          : m,
      );
      return { threads: { ...state.threads, [threadId]: updated } };
    }),
}));
