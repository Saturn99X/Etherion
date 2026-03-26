"use client"

import { create } from 'zustand'
import { nanoid } from 'nanoid'
import type { UploadFileItem } from '@/types/files/upload'

// Scope attachments per thread/branch using the same key format as useThreadPrefStore
const buildKey = (threadId: string, branchId?: string) => `${threadId}::${branchId ?? 'root'}`

interface ChatAttachmentsState {
  itemsByKey: Record<string, UploadFileItem[]>
  getItems: (threadId: string, branchId?: string) => UploadFileItem[]
  addFiles: (threadId: string, files: File[], branchId?: string) => Promise<void>
  remove: (threadId: string, id: string, branchId?: string) => void
  clear: (threadId: string, branchId?: string) => void
}

export const useChatAttachmentsStore = create<ChatAttachmentsState>((set, get) => ({
  itemsByKey: {},
  getItems: (threadId, branchId) => {
    const key = buildKey(threadId, branchId)
    return get().itemsByKey[key] || []
  },
  addFiles: async (threadId, files, branchId) => {
    const key = buildKey(threadId, branchId)

    const items: UploadFileItem[] = await Promise.all(
      files.map(async (file) => {
        const id = `${file.name}-${nanoid(6)}`
        const blobUrl = URL.createObjectURL(file)
        // Try to get a base64 data URL for potential future vision usage; safe to omit on failure
        let base64Url: string | undefined
        try {
          base64Url = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve(reader.result as string)
            reader.onerror = () => reject(reader.error)
            reader.readAsDataURL(file)
          })
        } catch {
          // ignore; previewUrl is enough for chips UI
        }
        return {
          id,
          file,
          status: 'success',
          previewUrl: blobUrl,
          base64Url,
        } as UploadFileItem
      })
    )

    set((state) => ({
      itemsByKey: {
        ...state.itemsByKey,
        [key]: [...(state.itemsByKey[key] || []), ...items],
      },
    }))
  },
  remove: (threadId, id, branchId) => {
    const key = buildKey(threadId, branchId)
    set((state) => ({
      itemsByKey: {
        ...state.itemsByKey,
        [key]: (state.itemsByKey[key] || []).filter((it) => it.id !== id),
      },
    }))
  },
  clear: (threadId, branchId) => {
    const key = buildKey(threadId, branchId)
    set((state) => {
      const next = { ...state.itemsByKey }
      delete next[key]
      return { itemsByKey: next }
    })
  },
}))
