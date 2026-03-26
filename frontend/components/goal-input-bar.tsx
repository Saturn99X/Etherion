"use client"

import type React from "react"
import { useRef, useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Send, X, Palette, Database, Paperclip } from "lucide-react"
import { GoalService } from "@/lib/services/goal-service"
import { useJobStore } from "@/lib/stores/job-store"
import { useToast } from "@/hooks/use-toast"
import { ModelProviderSelector } from "@/components/model-provider-selector"
import { AudioRecordButton } from "@/components/ui/audio-record-button"
import { useChatAttachmentsStore } from "@/lib/stores/chat-attachments-store"

// Mock toast hook for now if it doesn't exist
const useToastMock = () => ({
  toast: ({ title, description, variant }: { title: string; description: string; variant?: string }) => {
    console.log(`Toast: ${title} - ${description} (${variant})`);
  }
});

// NOTE: Attachments UI gated per Search-only policy. Default disabled.
const enableAttachments = process.env.NEXT_PUBLIC_ENABLE_CHAT_ATTACHMENTS === "true"

interface GoalInputBarProps {
  onSubmit?: (message: string, attachments: any[]) => void
  disabled?: boolean
  placeholder?: string
  threadId?: string
  branchId?: string
  allowPlatformEntry?: boolean
  autoFocus?: boolean
  planMode?: boolean
  searchForce?: boolean
  agentTeamId?: string
  onJobStarted?: (args: { jobId: string; threadId?: string; goal: string; planMode?: boolean; searchForce?: boolean }) => void
}

export function GoalInputBar({ onSubmit, disabled = false, placeholder = "Ask IO for anything...", threadId, branchId, allowPlatformEntry = true, autoFocus = false, planMode, searchForce, agentTeamId, onJobStarted }: GoalInputBarProps) {
  const [message, setMessage] = useState("")
  const [isExecuting, setIsExecuting] = useState(false)
  const [currentJobId, setCurrentJobId] = useState<string | undefined>(undefined)
  const [stopPending, setStopPending] = useState(false)
  const [selectedTone, setSelectedTone] = useState("Professional")
  const [selectedContext, setSelectedContext] = useState("General")
  const { addJob, subscribeToJob } = useJobStore()
  const { toast } = useToast() || useToastMock()
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const tId = threadId || "default"
  const getItems = useChatAttachmentsStore((s) => s.getItems)
  const addFiles = useChatAttachmentsStore((s) => s.addFiles)
  const removeItem = useChatAttachmentsStore((s) => s.remove)
  const clearItems = useChatAttachmentsStore((s) => s.clear)

  const handleSubmit = async () => {
    if (message.trim() && !disabled && !isExecuting) {
      setIsExecuting(true)

      try {
        // If platform entry is gated, route to Studio and stop here
        if (!allowPlatformEntry) {
          router.push("/studio")
          setIsExecuting(false)
          return
        }

        // Execute the goal
        const response = await GoalService.executeGoal({
          goal: message,
          context: `${selectedTone} tone, ${selectedContext} context`,
          output_format_instructions: "Provide a comprehensive response with actionable insights.",
          plan_mode: !!planMode,
          search_force: !!searchForce,
          agentTeamId,
        })

        if (response.success) {
          // Add job to tracking store, bound to this thread
          addJob(response.job_id, threadId)
          // Immediately subscribe to live status + execution trace for this job
          subscribeToJob(response.job_id)

          // Call original onSubmit if provided
          onSubmit?.(message, enableAttachments ? getItems(tId, branchId) : [])

          // Notify ThreadView to append assistant placeholder and optionally start streaming
          onJobStarted?.({ jobId: response.job_id, threadId, goal: message, planMode, searchForce })

          // Clear the input
          setMessage("")
          setCurrentJobId(response.job_id)
          // Clear ephemeral attachments for this thread
          if (enableAttachments) clearItems(tId, branchId)

          toast({
            title: "Goal Submitted",
            description: `Job ${response.job_id} has been queued for execution.`,
          })
        } else {
          throw new Error(response.message)
        }
      } catch (error) {
        console.error('Goal execution failed:', error)
        toast({
          title: "Execution Failed",
          description: error instanceof Error ? error.message : "Failed to execute goal",
          variant: "destructive",
        })
      } finally {
        setIsExecuting(false)
      }
    }
  }

  const stopExecution = async () => {
    if (currentJobId) {
      try {
        // Request server-side cancellation (STOP)
        await GoalService.cancelJob(currentJobId)
        // Hold disabled until ACK via subscription (status not running)
        setStopPending(true)
        setIsExecuting(true)
      } catch (e) {
        console.error('Failed to request cancelJob', e)
        setStopPending(false)
        setIsExecuting(false)
      }
    }
  }

  // Watch job status to release disabled state on STOP ACK or terminal states
  const jobs = useJobStore((s) => s.jobs)
  useEffect(() => {
    if (!stopPending || !currentJobId) return
    const status = jobs[currentJobId]?.status || ''
    const upper = String(status).toUpperCase()
    const terminal = ['CANCELLED', 'STOPPED', 'COMPLETED', 'FAILED', 'ERROR']
    if (terminal.includes(upper)) {
      setStopPending(false)
      setIsExecuting(false)
    }
  }, [stopPending, currentJobId, jobs])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleAttachClick = () => fileInputRef.current?.click()
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!enableAttachments) return
    const files = Array.from(e.target.files || [])
    if (files.length > 0) await addFiles(tId, files, branchId)
    // reset input so picking the same file later still triggers change
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  return (
    <div className="p-4">
      {/* Toolbar: provider/model selector, mic, and (optionally) attachments */}
      <div className="mb-2 flex items-center gap-2">
        <ModelProviderSelector threadId={tId} branchId={branchId} className="shrink-0" />
        <AudioRecordButton onText={(t) => setMessage((m) => (m ? `${m} ${t}` : t))} />
        {enableAttachments && (
          <>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 w-auto px-2 glass-button text-xs"
              onClick={handleAttachClick}
              title="Attach"
            >
              <Paperclip className="h-3 w-3 mr-2" /> Attach
            </Button>
            <input ref={fileInputRef} type="file" multiple onChange={handleFileChange} className="hidden" accept="image/*,video/*" />
          </>
        )}
      </div>

      <div className="mb-3">
        <Textarea
          placeholder={placeholder}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          className="min-h-[60px] max-h-[200px] resize-none border-0 glass text-white placeholder:text-white/50 focus-chromatic focus:glow-cyan transition-all duration-300"
          disabled={disabled || isExecuting}
          autoFocus={autoFocus}
        />
      </div>

      {/* Attachment chips row (optional) */}
      {enableAttachments && getItems(tId, branchId).length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {getItems(tId, branchId).map((f) => (
            <div key={f.id} className="flex items-center gap-2 glass-card rounded px-2 py-1">
              {f.previewUrl ? (
                <img src={f.previewUrl} alt={f.file.name} className="w-8 h-8 rounded object-cover" />
              ) : (
                <span className="text-xs text-white/80">{f.file.name}</span>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 text-white/70 hover:text-red-400"
                onClick={() => removeItem(tId, f.id, branchId)}
                title="Remove"
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Tone Selector */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                disabled={disabled}
                className="glass hover:glow-cyan transition-all duration-300 text-white/80 hover:text-white"
              >
                <Palette className="h-4 w-4 mr-2" />
                {selectedTone}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="glass-strong border-white/20">
              <DropdownMenuItem
                onClick={() => setSelectedTone("Professional")}
                className="text-white hover:glass-card focus:glass-card"
              >
                Professional
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setSelectedTone("Casual")}
                className="text-white hover:glass-card focus:glass-card"
              >
                Casual
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setSelectedTone("Creative")}
                className="text-white hover:glass-card focus:glass-card"
              >
                Creative
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setSelectedTone("Technical")}
                className="text-white hover:glass-card focus:glass-card"
              >
                Technical
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Context Picker */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                disabled={disabled}
                className="glass hover:glow-purple transition-all duration-300 text-white/80 hover:text-white"
              >
                <Database className="h-4 w-4 mr-2" />
                {selectedContext}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="glass-strong border-white/20">
              <DropdownMenuItem
                onClick={() => setSelectedContext("General")}
                className="text-white hover:glass-card focus:glass-card"
              >
                General
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setSelectedContext("Code")}
                className="text-white hover:glass-card focus:glass-card"
              >
                Code
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setSelectedContext("Research")}
                className="text-white hover:glass-card focus:glass-card"
              >
                Research
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setSelectedContext("Analysis")}
                className="text-white hover:glass-card focus:glass-card"
              >
                Analysis
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {isExecuting ? (
          <Button
            onClick={stopExecution}
            disabled={disabled}
            className="gap-2 glass text-white font-semibold hover:scale-105 transition-all duration-300 hover:glow-pink"
          >
            <X className="h-4 w-4" />
            Stop
          </Button>
        ) : (
          <Button
            onClick={handleSubmit}
            disabled={disabled || !message.trim()}
            className="gap-2 iridescent text-white font-semibold hover:scale-105 transition-all duration-300 glow-purple"
          >
            <Send className="h-4 w-4" />
            Execute Goal
          </Button>
        )}
      </div>
    </div>
  )
}
