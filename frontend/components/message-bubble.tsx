"use client"

import { useMemo, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Copy, RefreshCw, Trash2, User, Bot, GitBranch, Eye, Package, Volume2, VolumeX, Check, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { ArtifactPanel } from "./artifact-panel"
import { useThreadPrefStore, EMPTY_PREFS } from "@/lib/stores/thread-pref-store"
import ConfirmationModal from "@/components/ui/triggered-ui/confirmation-modals"
import { useToolcallStore } from "@/lib/stores/toolcall-store"
import { summarizeParams, redactParams } from "@/lib/lobe/toolcall-bridge"

interface MessageMetadata {
  cot?: string
  artifacts?: Array<{ kind: string; content?: string; title?: string }>
  toolExecId?: string
  showCot?: boolean
  showArtifacts?: boolean
}

interface Message {
  id: string
  role: "user" | "assistant" | "tool"
  content: string
  timestamp: Date
  metadata?: MessageMetadata
}

interface MessageBubbleProps {
  message: Message
  onCopy?: (content: string) => void
  onRetry?: (messageId: string) => void
  onDelete?: (messageId: string) => void
  onBranch?: () => void
  onToggleCot?: () => void
  onToggleArtifacts?: () => void
  statusChip?: string
  forkIndicator?: boolean
  threadId?: string
  branchId?: string
  onApproveTool?: (payload: { messageId: string; suggestionId: string; toolName: string; params: Record<string, any> }) => void
  onDenyTool?: (payload: { messageId: string; suggestionId: string }) => void
}

export function MessageBubble({ message, onCopy, onRetry, onDelete, onBranch, onToggleCot, onToggleArtifacts, statusChip, forkIndicator, threadId, branchId, onApproveTool, onDenyTool }: MessageBubbleProps) {
  const [isHovered, setIsHovered] = useState(false)
  const isUser = message.role === "user"

  // TTS state
  const [speaking, setSpeaking] = useState(false)
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null)

  // CRITICAL FIX: Use stable key and direct prefs access
  const prefKey = useMemo(() => `${threadId || 'default'}::${branchId ?? 'root'}`, [threadId, branchId])
  const prefs = useThreadPrefStore((s) => s.prefs[prefKey] || EMPTY_PREFS)
  const ttsVoicePref = prefs.ttsVoice
  const setPrefs = useThreadPrefStore((s) => s.setPrefs)

  const pickVoice = useMemo(() => {
    if (typeof window === 'undefined') return undefined
    const synth = window.speechSynthesis
    if (!synth) return undefined
    const voices = synth.getVoices() || []
    if (ttsVoicePref) return voices.find((v) => v.name === ttsVoicePref) || voices[0]
    const lang = (navigator as any).language || 'en-US'
    return voices.find((v) => v.lang?.toLowerCase().startsWith(lang.toLowerCase().slice(0, 2))) || voices[0]
  }, [ttsVoicePref])

  const stopTTS = () => {
    try {
      if (typeof window === 'undefined') return
      window.speechSynthesis?.cancel()
      utterRef.current = null
      setSpeaking(false)
    } catch { }
  }

  const startTTS = () => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return
    const text = (message.content || '').slice(0, 10_000) // basic guard
    const u = new SpeechSynthesisUtterance(text)
    const v = pickVoice
    if (v) {
      u.voice = v
      // persist chosen voice if not stored yet
      if (!ttsVoicePref) setPrefs(threadId || 'default', { ttsVoice: v.name }, branchId)
    }
    u.onend = () => setSpeaking(false)
    u.onerror = () => setSpeaking(false)
    utterRef.current = u
    setSpeaking(true)
    // voices might not be loaded immediately; defer start
    const synth = window.speechSynthesis
    const trySpeak = () => {
      try { synth.speak(u) } catch { }
    }
    if (synth.getVoices().length === 0) {
      const handler = () => { trySpeak(); synth.removeEventListener('voiceschanged', handler) }
      synth.addEventListener('voiceschanged', handler)
    } else {
      trySpeak()
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content)
    onCopy?.(message.content)
  }

  const handleRetry = () => {
    onRetry?.(message.id)
  }

  const handleDelete = () => {
    onDelete?.(message.id)
  }

  // Tool suggestions & invocations (Step 6)
  const threadKey = threadId || 'default'
  const suggestions = useToolcallStore((s) => s.getSuggestions(threadKey, message.id))
  const invocations = useToolcallStore((s) => s.getInvocations(threadKey, message.id))
  const clearSuggestion = useToolcallStore((s) => s.clearSuggestion)

  const [modalOpen, setModalOpen] = useState(false)
  const [selectedSuggestion, setSelectedSuggestion] = useState<null | { id: string; toolName: string; previewParams: Record<string, any> }>(null)

  const openApproveModal = (sugg: { id: string; toolName: string; previewParams: Record<string, any> }) => {
    setSelectedSuggestion(sugg)
    setModalOpen(true)
  }
  const closeApproveModal = () => {
    setModalOpen(false)
    setSelectedSuggestion(null)
  }

  // Sanitize and summarize CoT before rendering to avoid exposing raw chain-of-thought
  const sanitizeCot = (txt: string): string => {
    try {
      let t = (txt || '').toString()
      // Strip common raw markers
      t = t.replace(/<\/?(thought|reasoning|system|debug)[^>]*>/gi, '')
      // Mask sensitive tokens
      t = t.replace(/(api[_-]?key|secret|token|password)\s*[:=]\s*[\w-]{6,}/gi, '$1: ***')
      // Trim excessively long content
      if (t.length > 1200) t = t.slice(0, 1200) + '…'
      // Lightweight summary heuristic: keep first paragraph if multiple
      const parts = t.split(/\n{2,}/)
      if (parts.length > 1) t = parts[0]
      return t.trim()
    } catch {
      return ''
    }
  }

  const sanitizedCot = useMemo(() => sanitizeCot(message.metadata?.cot || ''), [message.metadata?.cot])

  return (
    <div
      className={cn("flex gap-3 group", isUser ? "justify-end" : "justify-start")}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Avatar - only show for assistant */}
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full glass-card glow-purple flex items-center justify-center">
          <Bot className="h-4 w-4 text-white" />
        </div>
      )}

      <div className={cn("flex flex-col gap-2 max-w-[80%]", isUser ? "items-end" : "items-start")}>
        {/* Subtle fork indicator at the branch start */}
        {!isUser && forkIndicator && (
          <div className="text-[10px] text-white/60 flex items-center gap-1">
            <GitBranch className="h-3 w-3" /> Branch start
          </div>
        )}
        <div
          className={cn(
            "rounded-lg px-4 py-3 text-sm relative transition-all duration-300",
            isUser
              ? "glass-card text-white glow-cyan hover:glow-hover"
              : "glass text-white/90 hover:glass-card hover:glow-hover",
          )}
        >
          <div className="whitespace-pre-wrap">{message.content}</div>
          <div className="absolute inset-0 rounded-lg shimmer-effect opacity-0 hover:opacity-30 transition-opacity duration-300 pointer-events-none" />
        </div>

        {/* Tool suggestion chips (assistant only) */}
        {!isUser && suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-1">
            {suggestions.map((s) => (
              <div key={s.id} className="flex items-center gap-2 text-[11px] glass rounded px-2 py-1 border border-white/10">
                <span className="font-medium text-white/90">{s.toolName}</span>
                <span className="text-white/60">{summarizeParams(s.previewParams)}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 px-2 glass hover:glow-cyan text-white/80 hover:text-white"
                  onClick={() => openApproveModal(s)}
                >
                  <Check className="h-3 w-3 mr-1" /> Approve
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 px-2 glass hover:glow-pink text-white/80 hover:text-white"
                  onClick={() => {
                    clearSuggestion(threadKey, message.id, s.id)
                    onDenyTool?.({ messageId: message.id, suggestionId: s.id })
                  }}
                >
                  <X className="h-3 w-3 mr-1" /> Deny
                </Button>
              </div>
            ))}
          </div>
        )}

        {/* Invocation status rows */}
        {!isUser && invocations.length > 0 && (
          <div className="flex flex-col gap-1 mt-1">
            {invocations.map((inv) => (
              <div key={inv.id} className="text-[11px] text-white/80 glass rounded px-2 py-1">
                <span className="font-medium">{inv.toolName}</span>
                <span className="ml-2">{inv.status}</span>
                {inv.error && <span className="ml-2 text-red-400">{inv.error}</span>}
              </div>
            ))}
          </div>
        )}

        {/* Inline status chip for tool/job runs */}
        {!isUser && statusChip && (
          <div className="text-[11px] text-white/70">
            {statusChip}
          </div>
        )}

        {/* Actions under bubble */}
        <div
          className={cn(
            "flex items-center gap-1 transition-all duration-300",
            isHovered ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2",
          )}
        >
          {/* TTS controls */}
          {!isUser && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-auto px-2 glass hover:glow-cyan transition-all duration-300 text-white/80 hover:text-white"
              onClick={() => (speaking ? stopTTS() : startTTS())}
            >
              {speaking ? <VolumeX className="h-3 w-3 mr-1" /> : <Volume2 className="h-3 w-3 mr-1" />} {speaking ? 'Stop' : 'Speak'}
            </Button>
          )}

          {/* Branch here */}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-auto px-2 glass hover:glow-purple transition-all duration-300 text-white/80 hover:text-white"
            onClick={() => onBranch?.()}
          >
            <GitBranch className="h-3 w-3 mr-1" /> Branch
          </Button>

          {/* View reasoning (CoT) */}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-auto px-2 glass hover:glow-cyan transition-all duration-300 text-white/80 hover:text-white"
            onClick={() => onToggleCot?.()}
          >
            <Eye className="h-3 w-3 mr-1" /> Reasoning
          </Button>

          {/* View artifacts */}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-auto px-2 glass hover:glow-pink transition-all duration-300 text-white/80 hover:text-white"
            onClick={() => onToggleArtifacts?.()}
          >
            <Package className="h-3 w-3 mr-1" /> Artifacts
          </Button>

          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 glass hover:glow-cyan transition-all duration-300 text-white/80 hover:text-white"
            onClick={handleCopy}
          >
            <Copy className="h-3 w-3" />
          </Button>

          {!isUser && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0 glass hover:glow-purple transition-all duration-300 text-white/80 hover:text-white"
              onClick={handleRetry}
            >
              <RefreshCw className="h-3 w-3" />
            </Button>
          )}

          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 glass hover:glow-pink transition-all duration-300 text-white/80 hover:text-red-400"
            onClick={handleDelete}
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>

        {/* Conditional reveals: Reasoning (CoT) */}
        {message.metadata?.showCot && sanitizedCot && (
          <div className={cn("w-full", isUser ? "items-end" : "items-start")}>
            <div className="mt-1 text-xs text-white/80 glass p-2 rounded">
              <span className="font-medium">Reasoning:</span> {sanitizedCot}
            </div>
          </div>
        )}

        {/* Conditional reveals: Artifacts */}
        {message.metadata?.showArtifacts && message.metadata?.artifacts && message.metadata.artifacts.length > 0 && (
          <div className={cn("w-full", isUser ? "items-end" : "items-start")}>
            <div className="mt-1">
              <ArtifactPanel artifacts={message.metadata.artifacts as any} />
            </div>
          </div>
        )}

        <span className="text-xs text-white/60 font-medium">
          {message.timestamp.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>

      {/* Avatar - only show for user */}
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full glass-card glow-cyan flex items-center justify-center">
          <User className="h-4 w-4 text-white" />
        </div>
      )}

      {/* Approval Confirmation Modal */}
      <ConfirmationModal
        open={!isUser && modalOpen}
        title={selectedSuggestion ? `Run tool: ${selectedSuggestion.toolName}` : 'Run tool'}
        message={selectedSuggestion ? `Params preview (redacted):\n\n${JSON.stringify(redactParams(selectedSuggestion.previewParams), null, 2)}` : ''}
        actions={[
          { label: 'Cancel', value: 'cancel', variant: 'secondary' },
          { label: 'Approve', value: 'approve', variant: 'primary' },
        ]}
        onClose={closeApproveModal}
        onAction={(val) => {
          if (val === 'approve' && selectedSuggestion) {
            onApproveTool?.({
              messageId: message.id,
              suggestionId: selectedSuggestion.id,
              toolName: selectedSuggestion.toolName,
              params: selectedSuggestion.previewParams,
            })
            clearSuggestion(threadKey, message.id, selectedSuggestion.id)
          }
          closeApproveModal()
        }}
      />
    </div>
  )
}

