import { nanoid } from 'nanoid'

// Frontend-only contracts for Step 6
export type ToolSuggestion = {
  id: string
  toolName: string
  previewParams: Record<string, any>
  reason?: string
  suggestedAt: string
  messageId: string
}

export type ToolInvocation = {
  id: string
  toolName: string
  params: Record<string, any>
  status: 'pending' | 'approved' | 'running' | 'succeeded' | 'failed'
  result?: any
  error?: string
  startedAt?: string
  finishedAt?: string
  relatedMessageId?: string
}

// Minimal redaction for params preview; credentials should never be here anyway
const SECRET_KEYS = ['api_key', 'apiKey', 'token', 'password', 'secret']
export const redactParams = (params: Record<string, any>): Record<string, any> => {
  const out: Record<string, any> = {}
  for (const [k, v] of Object.entries(params || {})) {
    if (SECRET_KEYS.includes(k)) out[k] = '***'
    else if (typeof v === 'object' && v !== null) out[k] = redactParams(v as any)
    else out[k] = v
  }
  return out
}

export const summarizeParams = (params: Record<string, any>): string => {
  try {
    const keys = Object.keys(params || {})
    if (keys.length === 0) return 'No params'
    const parts = keys.slice(0, 3).map((k) => `${k}: ${String(params[k]).slice(0, 30)}`)
    return parts.join(', ') + (keys.length > 3 ? '…' : '')
  } catch {
    return 'Params'
  }
}

// Heuristic stubber to create a demo suggestion from a prompt/goal (Step 6 demo only)
export const stubSuggestionsFromGoal = (goal: string, messageId: string): ToolSuggestion[] => {
  const trimmed = (goal || '').trim()
  if (!trimmed) return []
  const query = trimmed.slice(0, 128)
  return [
    {
      id: nanoid(),
      toolName: 'web_search',
      previewParams: { query },
      reason: 'Search the web to retrieve up-to-date context',
      suggestedAt: new Date().toISOString(),
      messageId,
    },
  ]
}
