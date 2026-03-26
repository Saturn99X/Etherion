import { create } from 'zustand'

// Etherion thread-level model/audio preferences
// KEY FORMAT: `${threadId}::${branchId ?? 'root'}`
export type ThreadPreferences = {
  provider?: string
  model?: string
  ttsVoice?: string
  sttEnabled?: boolean
}

export interface ThreadPrefState {
  // Map of threadId -> searchForce flag (existing behavior used by ThreadView)
  searchForce: Record<string, boolean>
  setSearchForce: (threadId: string, value: boolean) => void
  toggleSearchForce: (threadId: string) => void

  // New: per-thread/branch preferences for provider/model and TTS/STT
  prefs: Record<string, ThreadPreferences>
  getKey: (threadId: string, branchId?: string) => string
  getPrefs: (threadId: string, branchId?: string) => ThreadPreferences
  setPrefs: (threadId: string, patch: Partial<ThreadPreferences>, branchId?: string) => void
  clearPrefs: (threadId: string, branchId?: string) => void
}

// CRITICAL: Cached empty object to prevent infinite re-renders
// Zustand selectors must return stable references to avoid infinite loops
export const EMPTY_PREFS: ThreadPreferences = Object.freeze({})

export const useThreadPrefStore = create<ThreadPrefState>((set, get) => ({
  // Existing search toggle state
  searchForce: {},
  setSearchForce: (threadId, value) =>
    set((state) => ({ searchForce: { ...state.searchForce, [threadId]: !!value } })),
  toggleSearchForce: (threadId) => {
    const current = get().searchForce[threadId] || false
    set({ searchForce: { ...get().searchForce, [threadId]: !current } })
  },

  // New: provider/model and audio prefs
  prefs: {},
  getKey: (threadId: string, branchId?: string) => `${threadId}::${branchId ?? 'root'}`,
  getPrefs: (threadId: string, branchId?: string) => {
    const key = get().getKey(threadId, branchId)
    // FIXED: Return cached EMPTY_PREFS instead of new {} to prevent re-renders
    return get().prefs[key] || EMPTY_PREFS
  },
  setPrefs: (threadId: string, patch: Partial<ThreadPreferences>, branchId?: string) => {
    const key = get().getKey(threadId, branchId)
    const prev = get().prefs[key] || {}
    set({ prefs: { ...get().prefs, [key]: { ...prev, ...patch } } })
  },
  clearPrefs: (threadId: string, branchId?: string) => {
    const key = get().getKey(threadId, branchId)
    const next = { ...get().prefs }
    delete next[key]
    set({ prefs: next })
  },
}))

