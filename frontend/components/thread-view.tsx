"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { MessageBubble } from "./message-bubble"
import { GoalInputBar } from "./goal-input-bar"
import { ExecutionTraceUI } from "@/components/ui/triggered-ui/execution-trace-ui"
import { JobStatusTracker } from "./job-status-tracker"
import { AgentBlueprintUI } from "@/components/ui/triggered-ui/agent-blueprint-ui"
import { Menu, Plus, MessageSquare, ChevronLeft, ChevronRight } from "lucide-react"
import { useSearchParams } from "next/navigation"
import { useJobStore } from "@/lib/stores/job-store"
import { useThreadStore } from "@/lib/stores/useThreadStore"
import { fetchSSE } from "@/lib/lobe/streaming"
import { nanoid } from "nanoid"
import { useThreadPrefStore, EMPTY_PREFS } from "@/lib/stores/thread-pref-store"
import { useTeamStore, type Team } from "@/lib/stores/team-store"
import { useToolcallStore } from "@/lib/stores/toolcall-store"
import { stubSuggestionsFromGoal } from "@/lib/lobe/toolcall-bridge"
import { useApolloClient } from "@/components/apollo-provider"
import { EXECUTE_MCP_TOOL_MUTATION, LIST_AGENT_TEAMS_QUERY } from "@/lib/graphql-operations"
import { useAuthStore } from "@/lib/stores/auth-store"
import { decodeJwt } from "@/lib/jwt"

interface Thread {
  id: string
  title: string
  lastMessage: string
  timestamp: Date
}

function ThreadList({
  threads,
  activeThreadId,
  onThreadSelect,
}: {
  threads: Thread[]
  activeThreadId: string
  onThreadSelect: (threadId: string) => void
}) {
  return (
    <div className="h-full flex flex-col glass-strong">
      <div className="p-4 border-b border-border">
        <Button
          className="w-full gap-2 glass-button font-semibold hover:scale-105 transition-all duration-300 glow-purple"
          size="sm"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {threads.map((thread) => (
            <Button
              key={thread.id}
              variant={activeThreadId === thread.id ? "secondary" : "ghost"}
              className={`w-full justify-start text-left h-auto p-3 transition-all duration-300 ${activeThreadId === thread.id
                ? "glass-card glow-cyan text-foreground"
                : "text-muted-foreground hover:glass hover:text-foreground hover:glow-hover"
                }`}
              onClick={() => onThreadSelect(thread.id)}
            >
              <div className="flex flex-col items-start gap-1 min-w-0 flex-1">
                <div className="flex items-center gap-2 w-full">
                  <MessageSquare className="h-4 w-4 flex-shrink-0" />
                  <span className="font-medium text-sm truncate">{thread.title}</span>
                </div>
                <span className="text-xs text-muted-foreground truncate w-full">{thread.lastMessage}</span>
              </div>
            </Button>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

export function ThreadView() {
  const [activeThreadId, setActiveThreadId] = useState<string>("default")
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [timelineCollapsed, setTimelineCollapsed] = useState(false)
  const { jobs, removeJob } = useJobStore()
  const [threads, setThreads] = useState<Thread[]>([])
  const [selectedBranchId, setSelectedBranchId] = useState<string | undefined>(undefined)
  const { addMessage, createBranch, getMessagesByBranch, toggleCot, toggleArtifacts, updateMessageContent, setMessageMetadata } = useThreadStore()
  const [planMode, setPlanMode] = useState<boolean>(true)
  const searchForce = useThreadPrefStore((s) => s.searchForce[activeThreadId] || false)
  const toggleSearchForce = useThreadPrefStore((s) => s.toggleSearchForce)
  const { teams, selectedTeamId, setSelectedTeamId, setTeams } = useTeamStore()

  // CRITICAL FIX: Use useMemo to create stable key, then select from prefs directly
  const prefKey = useMemo(() => `${activeThreadId}::${selectedBranchId ?? 'root'}`, [activeThreadId, selectedBranchId])
  const currentPrefs = useThreadPrefStore((s) => s.prefs[prefKey] || EMPTY_PREFS)

  const client = useApolloClient()
  const { token } = useAuthStore()
  const searchParams = useSearchParams()

  // Initialize from URL params: thread and teamId
  useEffect(() => {
    try {
      const thread = searchParams?.get('thread')
      const teamId = searchParams?.get('teamId')
      if (thread && thread !== activeThreadId) setActiveThreadId(thread)
      if (teamId && teamId !== selectedTeamId) setSelectedTeamId(teamId)
    } catch { }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Load agent teams from GraphQL for selector (source of truth)
  useEffect(() => {
    client
      .query({ query: LIST_AGENT_TEAMS_QUERY, variables: { limit: 50, offset: 0 } })
      .then(({ data }) => {
        const list = (data?.listAgentTeams || []) as Array<any>
        const arr = list.map((t) => ({ id: String(t.id), name: t.name || String(t.id) }))
        setTeams(arr)
        if (!selectedTeamId && arr.length) setSelectedTeamId(arr[0].id)
      })
      .catch(() => { })
  }, [client, setTeams, selectedTeamId, setSelectedTeamId])

  const toolStore = useToolcallStore()

  const messagesFromStore = getMessagesByBranch(activeThreadId, selectedBranchId)
  const allMessagesForThread = getMessagesByBranch(activeThreadId)

  const branchIds = useMemo(() => {
    const ids = new Set<string>()
      ; (allMessagesForThread || []).forEach((m) => {
        if (m.branchId) ids.add(m.branchId)
      })
    return Array.from(ids)
  }, [allMessagesForThread])

  // find the first message id for each branch to mark a subtle fork indicator in UI
  const forkStartIds = useMemo(() => {
    const first: Record<string, string> = {}
    for (const m of allMessagesForThread || []) {
      if (m.branchId && !first[m.branchId]) first[m.branchId] = m.id
    }
    return new Set(Object.values(first))
  }, [allMessagesForThread])

  // Seed demo tool suggestions for assistant messages (client-only for Step 6)
  useEffect(() => {
    for (const m of messagesFromStore || []) {
      if (m.role === 'assistant' && (m.content || '').trim().length > 0) {
        const existing = toolStore.getSuggestions(activeThreadId, m.id)
        if (!existing || existing.length === 0) {
          const suggs = stubSuggestionsFromGoal(m.content, m.id)
          if (suggs.length) toolStore.seedSuggestions(activeThreadId, m.id, suggs)
        }
      }
    }
  }, [messagesFromStore, activeThreadId, toolStore])

  const getTenantId = (): number | null => {
    try {
      const t = token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null)
      if (!t) return null
      const payload = decodeJwt(t)
      const tid = (payload && ((payload as any).tenant_id ?? (payload as any).tenantId)) as number | string | undefined
      if (!tid) return null
      const n = Number(tid)
      return Number.isFinite(n) ? n : null
    } catch {
      return null
    }
  }

  const runTool = async (opts: { messageId: string; suggestionId: string; toolName: string; params: Record<string, any> }) => {
    const tenantId = getTenantId()
    if (!tenantId) {
      // Append a lightweight tool message error
      addMessage(activeThreadId, {
        id: nanoid(),
        role: 'tool',
        content: `Tool ${opts.toolName} failed: Missing tenant identity`,
        parentId: opts.messageId,
        branchId: selectedBranchId,
        timestamp: new Date().toISOString(),
        metadata: {},
      })
      return
    }

    const invId = nanoid()
    toolStore.startInvocation(activeThreadId, opts.messageId, {
      id: invId,
      toolName: opts.toolName,
      params: opts.params,
      status: 'approved',
      relatedMessageId: opts.messageId,
      startedAt: new Date().toISOString(),
    })

    try {
      toolStore.updateInvocation(activeThreadId, opts.messageId, invId, { status: 'running' })
      const { data } = await client.mutate({
        mutation: EXECUTE_MCP_TOOL_MUTATION,
        variables: {
          tool_name: opts.toolName,
          params: JSON.stringify({
            tenant_id: tenantId,
            search_force: !!searchForce,
            ...(selectedTeamId ? { agent_team_id: selectedTeamId } : {}),
            ...opts.params,
          }),
        },
      })
      const result = (data as any)?.executeMCPTool
      if (result?.success) {
        toolStore.updateInvocation(activeThreadId, opts.messageId, invId, {
          status: 'succeeded',
          result: result.result ?? result.toolOutput,
          finishedAt: new Date().toISOString(),
        })
        let content: string = 'Tool executed successfully.'
        let artifacts: any[] | undefined
        const output = result.result ?? result.toolOutput
        try {
          const obj = typeof output === 'string' ? JSON.parse(output) : output
          if (obj && typeof obj === 'object' && (obj.kind === 'html' || obj.kind === 'svg' || obj.kind === 'doc' || obj.kind === 'code') && typeof obj.content === 'string') {
            artifacts = [{ kind: obj.kind, content: obj.content, title: obj.title }]
            content = obj.summary || `Produced ${obj.kind} artifact`
          } else if (typeof output === 'string') {
            content = output
          } else if (output != null) {
            content = JSON.stringify(output)
          }
        } catch {
          if (typeof output === 'string') content = output
        }
        addMessage(activeThreadId, {
          id: nanoid(),
          role: 'tool',
          content,
          parentId: opts.messageId,
          branchId: selectedBranchId,
          timestamp: new Date().toISOString(),
          metadata: artifacts ? { artifacts } as any : {},
        })
      } else {
        const errMsg = result?.errorMessage || 'Execution failed'
        toolStore.updateInvocation(activeThreadId, opts.messageId, invId, {
          status: 'failed',
          error: errMsg,
          finishedAt: new Date().toISOString(),
        })
        addMessage(activeThreadId, {
          id: nanoid(),
          role: 'tool',
          content: `Tool ${opts.toolName} failed: ${errMsg}`,
          parentId: opts.messageId,
          branchId: selectedBranchId,
          timestamp: new Date().toISOString(),
          metadata: {},
        })
      }
    } catch (e: any) {
      const errMsg = String(e?.message || e)
      toolStore.updateInvocation(activeThreadId, opts.messageId, invId, {
        status: 'failed',
        error: errMsg,
        finishedAt: new Date().toISOString(),
      })
      addMessage(activeThreadId, {
        id: nanoid(),
        role: 'tool',
        content: `Tool ${opts.toolName} error: ${errMsg}`,
        parentId: opts.messageId,
        branchId: selectedBranchId,
        timestamp: new Date().toISOString(),
        metadata: {},
      })
    }
  }

  // Map job -> assistant placeholder message id for streaming/final update
  const [jobToMsg, setJobToMsg] = useState<Record<string, string>>({})

  // Optional streaming endpoint
  const streamUrl = process.env.NEXT_PUBLIC_CHAT_SSE_URL

  const startStreaming = async (jobId: string, messageId: string) => {
    if (!streamUrl) return; // fallback mode (no streaming)

    let aggText = ""
    let aggReason = ""
    try {
      await fetchSSE(streamUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId }),
        onMessageHandle: (chunk: any) => {
          if (chunk.type === 'text' && chunk.text) {
            aggText += chunk.text
            updateMessageContent(activeThreadId, messageId, aggText)
          } else if (chunk.type === 'reasoning' && chunk.text) {
            aggReason += chunk.text
            setMessageMetadata(activeThreadId, messageId, { cot: aggReason })
          }
        },
      })
    } catch (e) {
      console.warn('Streaming failed, will rely on final append', e)
    }
  }

  const handleJobStarted = ({ jobId, threadId, goal }: { jobId: string; threadId?: string; goal: string }) => {
    const tId = threadId || activeThreadId
    const placeholderId = nanoid()
    // Append assistant placeholder immediately
    addMessage(tId, {
      id: placeholderId,
      role: "assistant",
      content: "",
      parentId: undefined,
      branchId: selectedBranchId,
      timestamp: new Date().toISOString(),
      metadata: { toolExecId: jobId },
    })

    setJobToMsg((m) => ({ ...m, [jobId]: placeholderId }))

    // Try streaming if endpoint configured
    startStreaming(jobId, placeholderId)
  }

  const handleSendMessage = (message: string, attachments: any[]) => {
    // Append user message immediately (rolling chat UX)
    addMessage(activeThreadId, {
      id: nanoid(),
      role: "user",
      content: message,
      parentId: undefined,
      branchId: selectedBranchId,
      timestamp: new Date().toISOString(),
      metadata: {},
    })
    // Execution/trace is handled by GoalInputBar via GoalService and Job store
  }

  // When a job completes, if we have no streaming, append final assistant message from archived summary
  useEffect(() => {
    const entries = Object.entries(jobs)
    for (const [jobId, job] of entries) {
      const msgId = jobToMsg[jobId]
      if (msgId && job.isCompleted) {
        // fetch final summary once and clear mapping
        import('@/lib/services/goal-service').then(async ({ GoalService }) => {
          const final = await GoalService.getArchivedTraceSummary(jobId)
          if (final) updateMessageContent(activeThreadId, msgId, final)
        })
        setJobToMsg((m) => {
          const { [jobId]: _rm, ...rest } = m
          return rest
        })
      }
    }
  }, [jobs, jobToMsg, activeThreadId, updateMessageContent])

  return (
    <div className="flex h-full relative">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-gradient-to-r from-purple-500/15 to-cyan-500/15 rounded-full blur-3xl float-animation" />
        <div
          className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-pink-500/15 to-blue-500/15 rounded-full blur-3xl float-animation"
          style={{ animationDelay: "2s" }}
        />
        <div
          className="absolute top-1/2 left-1/2 w-64 h-64 bg-gradient-to-r from-yellow-500/10 to-purple-500/10 rounded-full blur-3xl float-animation"
          style={{ animationDelay: "4s" }}
        />
      </div>

      {/* Desktop Timeline Sidebar */}
      <div
        className={`hidden md:flex border-r border-border transition-all duration-300 z-10 ${timelineCollapsed ? "w-12" : "w-80"
          }`}
      >
        {timelineCollapsed ? (
          <div className="flex flex-col items-center p-2 glass-strong">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setTimelineCollapsed(false)}
              className="mb-2 glass-button hover:glow-cyan transition-all duration-300"
            >
              <ChevronRight className="h-4 w-4 text-foreground" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="mb-2 glass-button hover:glow-purple transition-all duration-300"
            >
              <Plus className="h-4 w-4 text-foreground" />
            </Button>
            {threads.map((thread) => (
              <Button
                key={thread.id}
                variant={activeThreadId === thread.id ? "secondary" : "ghost"}
                size="sm"
                className={`mb-1 w-8 h-8 p-0 transition-all duration-300 ${activeThreadId === thread.id ? "glass-card glow-purple" : "glass-button hover:glow-hover"
                  }`}
                onClick={() => setActiveThreadId(thread.id)}
              >
                <MessageSquare className="h-4 w-4 text-foreground" />
              </Button>
            ))}
          </div>
        ) : (
          <div className="w-full">
            <div className="flex items-center justify-between p-4 border-b border-border glass-strong">
              <Button
                className="flex-1 gap-2 mr-2 glass-button font-semibold hover:scale-105 transition-all duration-300 glow-purple"
                size="sm"
              >
                <Plus className="h-4 w-4" />
                New Chat
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setTimelineCollapsed(true)}
                className="glass-button hover:glow-cyan transition-all duration-300"
              >
                <ChevronLeft className="h-4 w-4 text-foreground" />
              </Button>
            </div>
            <ThreadList threads={threads} activeThreadId={activeThreadId} onThreadSelect={setActiveThreadId} />
          </div>
        )}
      </div>

      {/* Mobile Sidebar */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-80 p-0 glass-strong border-border">
          <ThreadList
            threads={threads}
            activeThreadId={activeThreadId}
            onThreadSelect={(id) => {
              setActiveThreadId(id)
              setSidebarOpen(false)
            }}
          />
        </SheetContent>
      </Sheet>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col relative z-10">
        {/* Mobile Header */}
        <div className="md:hidden flex items-center gap-3 p-4 border-b border-border glass">
          <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="text-foreground hover:glow">
                <Menu className="h-4 w-4" />
              </Button>
            </SheetTrigger>
          </Sheet>
          <h1 className="font-semibold text-foreground">
            {threads.find((t) => t.id === activeThreadId)?.title || "Chat"}
          </h1>
        </div>

        {/* Active Job Trackers */}
        {Object.keys(jobs).length > 0 && (
          <div className="border-b border-border p-4">
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-white/90">Active Jobs</h3>
              <div className="grid gap-3">
                {Object.entries(jobs)
                  .filter(([_, job]) => !job.isCompleted && !job.isFailed)
                  .map(([jobId, job]) => (
                    <JobStatusTracker
                      key={jobId}
                      jobId={jobId}
                      onClose={() => removeJob(jobId)}
                      className="max-w-2xl"
                    />
                  ))}
              </div>
            </div>
          </div>
        )}

        {/* Header Controls: Plan/Act, Search toggle, Team selector (left-aligned) */}
        <div className="border-b border-border p-3 glass-strong">
          <div className="max-w-4xl mx-auto flex items-center gap-2">
            <div className="flex items-center gap-1">
              <Button
                variant={planMode ? "secondary" : "ghost"}
                size="sm"
                className="glass-button"
                onClick={() => setPlanMode(true)}
              >
                Plan
              </Button>
              <Button
                variant={!planMode ? "secondary" : "ghost"}
                size="sm"
                className="glass-button"
                onClick={() => setPlanMode(false)}
              >
                Act
              </Button>
            </div>
            <div className="ml-3">
              <Button
                variant={searchForce ? "secondary" : "ghost"}
                size="sm"
                className="glass-button"
                onClick={() => toggleSearchForce(activeThreadId)}
              >
                {`Search: ${searchForce ? "On" : "Off"}`}
              </Button>
            </div>
            {/* Team selector — left side per spec */}
            <div className="ml-3 min-w-[200px]">
              <Select value={selectedTeamId || undefined} onValueChange={(v) => setSelectedTeamId(v)}>
                <SelectTrigger className="h-8 glass-button text-sm">
                  <SelectValue placeholder="Select team" />
                </SelectTrigger>
                <SelectContent className="glass-strong border-border">
                  {teams.map((t: Team) => (
                    <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {/* Provider/Model badge for current thread/branch (right-aligned) */}
            {(currentPrefs.provider || currentPrefs.model) && (
              <div className="ml-auto text-[11px] text-white/70 glass rounded px-2 py-1">
                {(currentPrefs.provider || 'provider') + ' • ' + (currentPrefs.model || 'model')}
              </div>
            )}
          </div>
        </div>

        {/* Branches selector */}
        {branchIds.length > 0 && (
          <div className="border-b border-border p-2 glass-subtle">
            <div className="max-w-4xl mx-auto flex items-center gap-2">
              <span className="text-xs text-white/70">Branches:</span>
              <Button
                size="sm"
                variant={!selectedBranchId ? 'secondary' : 'ghost'}
                className="h-7 px-2 glass-button"
                onClick={() => setSelectedBranchId(undefined)}
              >All</Button>
              {branchIds.map((bid) => (
                <Button
                  key={bid}
                  size="sm"
                  variant={selectedBranchId === bid ? 'secondary' : 'ghost'}
                  className="h-7 px-2 glass-button"
                  onClick={() => setSelectedBranchId(bid)}
                >{bid.slice(0, 6)}</Button>
              ))}
            </div>
          </div>
        )}

        {/* Messages with integrated execution traces (per-thread job traces) */}
        <ScrollArea className="flex-1 p-4">
          <div className="space-y-4 max-w-4xl mx-auto">
            {messagesFromStore.length === 0 ? (
              <div className="text-center text-muted-foreground py-12">
                <p>No messages yet. Start a new chat.</p>
              </div>
            ) : (
              <>
                {messagesFromStore.map((m) => {
                  const jobId = m.metadata?.toolExecId
                  const job = jobId ? jobs[jobId] : undefined
                  const statusChip = job
                    ? job.isCompleted
                      ? 'Completed'
                      : job.isFailed
                        ? 'Failed'
                        : `${job.status}${job.progressPercentage ? ` ${Math.round(job.progressPercentage)}%` : ''}`
                    : undefined
                  return (
                    <MessageBubble
                      key={m.id}
                      statusChip={statusChip}
                      message={{ id: m.id, role: m.role as any, content: m.content, timestamp: new Date(m.timestamp), metadata: m.metadata as any }}
                      threadId={activeThreadId}
                      branchId={selectedBranchId}
                      forkIndicator={forkStartIds.has(m.id)}
                      onBranch={() => {
                        const bid = createBranch(activeThreadId, m.id)
                        setSelectedBranchId(bid)
                        // immediately append an empty user turn in the new branch per spec
                        addMessage(activeThreadId, {
                          id: nanoid(),
                          role: 'user',
                          content: '',
                          parentId: m.id,
                          branchId: bid,
                          timestamp: new Date().toISOString(),
                          metadata: {},
                        })
                      }}
                      onToggleCot={() => toggleCot(activeThreadId, m.id)}
                      onToggleArtifacts={() => toggleArtifacts(activeThreadId, m.id)}
                      onApproveTool={(p) => runTool(p)}
                      onDenyTool={() => { /* no-op; suggestions already cleared in child */ }}
                    />
                  )
                })}
              </>
            )}

            {/* Render an ExecutionTraceUI for each active job in this thread */}
            {Object.entries(jobs)
              .filter(([_, job]) => job.threadId === activeThreadId && !job.isCompleted && !job.isFailed)
              .map(([jobId]) => {
                const buildToolHints = () => {
                  const hints: { threadId: string; messageId: string; invocationId: string; toolName: string }[] = []
                  for (const m of messagesFromStore || []) {
                    const invs = toolStore.getInvocations(activeThreadId, m.id)
                    for (const inv of invs) {
                      if (inv.status === 'approved' || inv.status === 'running') {
                        hints.push({ threadId: activeThreadId, messageId: m.id, invocationId: inv.id, toolName: inv.toolName })
                      }
                    }
                  }
                  return hints
                }
                return (
                  <div key={jobId} className="my-6 space-y-4">
                    <ExecutionTraceUI
                      jobId={jobId}
                      toolHints={buildToolHints()}
                      showToolBadge
                      onToolEvent={(hint, _evt, phase) => {
                        if (phase === 'running') {
                          toolStore.updateInvocation(activeThreadId, hint.messageId, hint.invocationId, { status: 'running' })
                        } else if (phase === 'succeeded') {
                          toolStore.updateInvocation(activeThreadId, hint.messageId, hint.invocationId, { status: 'succeeded', finishedAt: new Date().toISOString() })
                        } else if (phase === 'failed') {
                          toolStore.updateInvocation(activeThreadId, hint.messageId, hint.invocationId, { status: 'failed', finishedAt: new Date().toISOString() })
                        }
                      }}
                    />
                    <AgentBlueprintUI jobId={jobId} />
                  </div>
                )
              })}
          </div>
        </ScrollArea>

        {/* Input Bar */}
        <div className="border-t border-border glass">
          <div className="max-w-4xl mx-auto">
            <GoalInputBar
              onSubmit={handleSendMessage}
              threadId={activeThreadId}
              branchId={selectedBranchId}
              allowPlatformEntry={true}
              planMode={planMode}
              searchForce={searchForce}
              agentTeamId={selectedTeamId || undefined}
              onJobStarted={handleJobStarted}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
