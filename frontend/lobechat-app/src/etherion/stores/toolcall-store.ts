import { create } from 'zustand'
import type { ToolInvocation, ToolSuggestion } from '@etherion/lib/lobe/toolcall-bridge'

interface ToolcallState {
  suggestions: Record<string, Record<string, ToolSuggestion[]>> // threadId -> messageId -> suggestions
  invocations: Record<string, Record<string, ToolInvocation[]>> // threadId -> messageId -> invocations

  // queries
  getSuggestions: (threadId: string, messageId: string) => ToolSuggestion[]
  getInvocations: (threadId: string, messageId: string) => ToolInvocation[]

  // mutations
  seedSuggestions: (threadId: string, messageId: string, suggestions: ToolSuggestion[]) => void
  clearSuggestion: (threadId: string, messageId: string, suggestionId: string) => void
  startInvocation: (threadId: string, messageId: string, inv: ToolInvocation) => void
  updateInvocation: (
    threadId: string,
    messageId: string,
    invocationId: string,
    patch: Partial<ToolInvocation>
  ) => void
}

export const useToolcallStore = create<ToolcallState>((set, get) => ({
  suggestions: {},
  invocations: {},

  getSuggestions: (threadId, messageId) => {
    const s = get().suggestions[threadId]?.[messageId]
    return s ? [...s] : []
  },
  getInvocations: (threadId, messageId) => {
    const i = get().invocations[threadId]?.[messageId]
    return i ? [...i] : []
  },

  seedSuggestions: (threadId, messageId, suggestions) =>
    set((state) => {
      const byThread = state.suggestions[threadId] || {}
      const existing = byThread[messageId]
      if (existing && existing.length > 0) return state
      return {
        suggestions: {
          ...state.suggestions,
          [threadId]: { ...byThread, [messageId]: [...suggestions] },
        },
      }
    }),

  clearSuggestion: (threadId, messageId, suggestionId) =>
    set((state) => {
      const byThread = state.suggestions[threadId] || {}
      const list = byThread[messageId] || []
      return {
        suggestions: {
          ...state.suggestions,
          [threadId]: { ...byThread, [messageId]: list.filter((s) => s.id !== suggestionId) },
        },
      }
    }),

  startInvocation: (threadId, messageId, inv) =>
    set((state) => {
      const byThread = state.invocations[threadId] || {}
      const list = byThread[messageId] || []
      return {
        invocations: {
          ...state.invocations,
          [threadId]: { ...byThread, [messageId]: [...list, inv] },
        },
      }
    }),

  updateInvocation: (threadId, messageId, invocationId, patch) =>
    set((state) => {
      const byThread = state.invocations[threadId] || {}
      const list = byThread[messageId] || []
      const updated = list.map((x) => (x.id === invocationId ? { ...x, ...patch } : x))
      return {
        invocations: {
          ...state.invocations,
          [threadId]: { ...byThread, [messageId]: updated },
        },
      }
    }),
}))
