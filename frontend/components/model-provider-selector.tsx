"use client"

import { useMemo } from 'react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useThreadPrefStore, EMPTY_PREFS } from '@/lib/stores/thread-pref-store'
import { LOBE_DEFAULT_MODEL_LIST } from 'model-bank'
import type { LobeDefaultAiModelListItem } from 'model-bank'

interface Props {
  threadId: string
  branchId?: string
  className?: string
}

// Simple title-case helper for provider id labels
const titleCase = (s: string) => s.replace(/(^|[\s-_])([a-z])/g, (_, p1, p2) => p1 + p2.toUpperCase())

export function ModelProviderSelector({ threadId, branchId, className }: Props) {
  // CRITICAL FIX: Use stable key and direct prefs access
  const prefKey = useMemo(() => `${threadId}::${branchId ?? 'root'}`, [threadId, branchId])
  const prefs = useThreadPrefStore((s) => s.prefs[prefKey] || EMPTY_PREFS)
  const setPrefs = useThreadPrefStore((s) => s.setPrefs)

  const chatModels: LobeDefaultAiModelListItem[] = useMemo(
    () => (LOBE_DEFAULT_MODEL_LIST.filter((m) => m.type === 'chat') as LobeDefaultAiModelListItem[]),
    [],
  )

  const providerOptions: string[] = useMemo(() => {
    const set = new Set<string>(chatModels.map((m) => m.providerId))
    return Array.from(set).sort()
  }, [chatModels])

  const modelsByProvider = useMemo(() => {
    const map = new Map<string, LobeDefaultAiModelListItem[]>()
    for (const m of chatModels) {
      const arr = map.get(m.providerId) || []
      arr.push(m)
      map.set(m.providerId, arr)
    }
    // sort models by display name then id for stability
    for (const [k, arr] of map.entries()) {
      arr.sort((a, b) => (a.displayName || a.id).localeCompare(b.displayName || b.id))
      map.set(k, arr)
    }
    return map
  }, [chatModels])

  const provider: string = prefs.provider || providerOptions[0]
  const availableModels = modelsByProvider.get(provider) || []
  const model: string = prefs.model || (availableModels[0]?.id || '')

  return (
    <div className={className}>
      <div className="flex items-center gap-2">
        <Select
          value={provider}
          onValueChange={(v: string) => {
            const firstModel = modelsByProvider.get(v)?.[0]?.id
            setPrefs(threadId, { provider: v, model: firstModel }, branchId)
          }}
        >
          <SelectTrigger className="h-8 glass-button text-xs min-w-[140px]">
            <SelectValue placeholder="Provider" />
          </SelectTrigger>
          <SelectContent className="glass-strong border-border">
            {providerOptions.map((p: string) => (
              <SelectItem key={p} value={p} className="text-xs">
                {titleCase(p)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={model}
          onValueChange={(v: string) => setPrefs(threadId, { model: v, provider }, branchId)}
        >
          <SelectTrigger className="h-8 glass-button text-xs min-w-[160px]">
            <SelectValue placeholder="Model" />
          </SelectTrigger>
          <SelectContent className="max-h-72 glass-strong border-border">
            {availableModels.map((m: LobeDefaultAiModelListItem) => (
              <SelectItem key={m.id} value={m.id} className="text-xs">
                {m.displayName || m.id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
