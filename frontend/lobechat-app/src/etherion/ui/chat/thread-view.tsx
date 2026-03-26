"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { ActionIcon, Avatar } from '@lobehub/ui';
import { ChatInputArea, ChatItem } from '@lobehub/ui/chat';
import { Button, Select, Space, Tag, Drawer } from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Menu, Plus, MessageSquare, ChevronLeft, ChevronRight } from "lucide-react"
import { useSearchParams } from "next/navigation"

import { MessageBubble } from "./message-bubble"
import { GoalInputBar } from "./goal-input-bar"
import { JobStatusTracker } from "../dashboard/job-status-tracker"
import { ExecutionTraceUI } from "../panels/execution-trace-panel"
import { AgentBlueprintUI } from "../panels/agent-blueprint-preview"

import { useJobStore } from "@etherion/stores/job-store"
import { useThreadStore } from "@etherion/stores/useThreadStore"
import { fetchSSE } from "@etherion/lib/lobe/streaming"
import { nanoid } from "nanoid"
import { useThreadPrefStore, EMPTY_PREFS } from "@etherion/stores/thread-pref-store"
import { useTeamStore, type Team } from "@etherion/stores/team-store"
import { useToolcallStore } from "@etherion/stores/toolcall-store"
import { stubSuggestionsFromGoal } from "@etherion/lib/lobe/toolcall-bridge"
import { useApolloClient } from "@etherion/ui/layout/apollo-provider"
import { EXECUTE_MCP_TOOL_MUTATION, LIST_AGENT_TEAMS_QUERY } from "@etherion/lib/graphql-operations"
import { useAuthStore } from "@etherion/stores/auth-store"
import { decodeJwt } from "@etherion/lib/jwt"

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    display: flex;
    height: 100%;
    position: relative;
    background: ${token.colorBgLayout};
  `,
  sidebar: css`
    border-right: 1px solid ${token.colorBorder};
    transition: width 0.3s;
    background: ${token.colorBgContainer};
    display: flex;
    flex-direction: column;
  `,
  mainArea: css`
    flex: 1;
    display: flex;
    flex-direction: column;
    position: relative;
    z-index: 10;
  `,
  header: css`
    border-bottom: 1px solid ${token.colorBorder};
    padding: 12px;
    background: ${token.colorBgContainer};
  `,
  scrollArea: css`
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  `,
  inputWrapper: css`
    border-top: 1px solid ${token.colorBorder};
    background: ${token.colorBgContainer};
    padding: 12px;
  `,
  threadItem: css`
    padding: 12px;
    border-radius: ${token.borderRadius}px;
    cursor: pointer;
    transition: all 0.2s;
    &:hover {
      background: ${token.colorFillTertiary};
    }
  `,
  threadItemActive: css`
    background: ${token.colorFillSecondary};
  `
}));

interface ThreadViewProps {
  threadId?: string;
  mode?: 'default' | 'foundry'; // 'foundry' locks to Platform Orchestrator
  initialGoal?: string; // Auto-send an initial goal if provided
}

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
  const { styles, cx } = useStyles();

  return (
    <Flexbox className="h-full" direction="vertical">
      <div className="p-4 border-b border-border">
        <Button
          type="primary"
          icon={<Plus size={16} />}
          block
          onClick={() => {/* Handled by parent or dispatcher */ }}
        >
          New Chat
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        <Space direction="vertical" className="w-full" size={4}>
          {threads.map((thread) => (
            <div
              key={thread.id}
              className={cx(styles.threadItem, activeThreadId === thread.id && styles.threadItemActive)}
              onClick={() => onThreadSelect(thread.id)}
            >
              <Flexbox direction="vertical" gap={2}>
                <Flexbox direction="horizontal" align="center" gap={8}>
                  <MessageSquare size={14} />
                  <div className="font-medium text-sm truncate">{thread.title}</div>
                </Flexbox>
                <div className="text-xs text-muted-foreground truncate">{thread.lastMessage}</div>
              </Flexbox>
            </div>
          ))}
        </Space>
      </div>
    </Flexbox>
  )
}

export function ThreadView({ threadId: propsThreadId, mode = 'default', initialGoal }: ThreadViewProps) {
  const { styles, cx } = useStyles();
  const [activeThreadId, setActiveThreadId] = useState<string>("default")
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [timelineCollapsed, setTimelineCollapsed] = useState(false)
  const { jobs, removeJob } = useJobStore()
  const [threads, setThreads] = useState<Thread[]>([])
  const [selectedBranchId, setSelectedBranchId] = useState<string | undefined>(undefined)
  const {
    addMessage,
    createBranch,
    getMessagesByBranch,
    toggleCot,
    toggleArtifacts,
    updateMessageContent,
    setMessageMetadata
  } = useThreadStore()
  const [planMode, setPlanMode] = useState<boolean>(true)
  const searchForce = useThreadPrefStore((s) => s.searchForce[activeThreadId] || false)
  const toggleSearchForce = useThreadPrefStore((s) => s.toggleSearchForce)
  const { teams, selectedTeamId, setSelectedTeamId, setTeams } = useTeamStore()

  const prefKey = useMemo(() => `${activeThreadId}::${selectedBranchId ?? 'root'}`, [activeThreadId, selectedBranchId])
  const currentPrefs = useThreadPrefStore((s) => s.prefs[prefKey] || EMPTY_PREFS)

  const client = useApolloClient()
  const { token } = useAuthStore()
  const searchParams = useSearchParams()

  useEffect(() => {
    try {
      const thread = searchParams?.get('thread')
      const teamId = searchParams?.get('teamId')
      if (thread && thread !== activeThreadId) setActiveThreadId(thread)
      if (teamId && teamId !== selectedTeamId) setSelectedTeamId(teamId)
    } catch { }
  }, [searchParams, activeThreadId, selectedTeamId, setSelectedTeamId])

  useEffect(() => {
    client
      .query({ query: LIST_AGENT_TEAMS_QUERY, variables: { limit: 50, offset: 0 } })
      .then(({ data }) => {
        const list = (data?.listAgentTeams || []) as Array<any>
        const arr = list.map((t) => ({ id: String(t.id), name: t.name || String(t.id) }))
        setTeams(arr)

        // In Foundry mode, we strictly stay on IO (undefined).
        // In Default mode, we auto-select the first team if none selected.
        if (mode === 'default' && !selectedTeamId && arr.length) {
          setSelectedTeamId(arr[0].id)
        }
      })
      .catch(() => { })
  }, [client, setTeams, selectedTeamId, setSelectedTeamId, mode])

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

  const forkStartIds = useMemo(() => {
    const first: Record<string, string> = {}
    for (const m of allMessagesForThread || []) {
      if (m.branchId && !first[m.branchId]) first[m.branchId] = m.id
    }
    return new Set(Object.values(first))
  }, [allMessagesForThread])

  const getTenantId = (): number | null => {
    try {
      const t = token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null)
      if (!t) return null
      const payload = decodeJwt(t)
      const tid = (payload && ((payload as any).tenant_id ?? (payload as any).tenantId)) as number | string | undefined
      if (!tid) return null
      return Number(tid)
    } catch { return null }
  }

  const runTool = async (opts: { messageId: string; suggestionId: string; toolName: string; params: Record<string, any> }) => {
    const tenantId = getTenantId()
    if (!tenantId) {
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
          if (obj && typeof obj === 'object') {
            artifacts = [{ kind: obj.kind, content: obj.content, title: obj.title }]
            content = obj.summary || `Produced ${obj.kind} artifact`
          } else if (typeof output === 'string') content = output
        } catch { content = String(output) }
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
        toolStore.updateInvocation(activeThreadId, opts.messageId, invId, { status: 'failed', error: errMsg, finishedAt: new Date().toISOString() })
      }
    } catch (e: any) {
      toolStore.updateInvocation(activeThreadId, opts.messageId, invId, { status: 'failed', error: String(e), finishedAt: new Date().toISOString() })
    }
  }

  const [jobToMsg, setJobToMsg] = useState<Record<string, string>>({})
  const streamUrl = process.env.NEXT_PUBLIC_CHAT_SSE_URL

  const startStreaming = async (jobId: string, messageId: string) => {
    if (!streamUrl) return
    let aggText = ""
    let aggReason = ""
    try {
      await fetchSSE(streamUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId }),
        onMessageHandle: (chunk: any) => {
          if (chunk.type === 'text') {
            aggText += chunk.text
            updateMessageContent(activeThreadId, messageId, aggText)
          } else if (chunk.type === 'reasoning') {
            aggReason += chunk.text
            setMessageMetadata(activeThreadId, messageId, { cot: aggReason })
          }
        },
      })
    } catch { }
  }

  const handleJobStarted = ({ jobId, threadId }: { jobId: string; threadId?: string }) => {
    const tId = threadId || activeThreadId
    const placeholderId = nanoid()
    addMessage(tId, {
      id: placeholderId,
      role: "assistant",
      content: "",
      branchId: selectedBranchId,
      timestamp: new Date().toISOString(),
      metadata: { toolExecId: jobId },
    })
    setJobToMsg((m) => ({ ...m, [jobId]: placeholderId }))
    startStreaming(jobId, placeholderId)
  }

  const handleSendMessage = (message: string) => {
    addMessage(activeThreadId, {
      id: nanoid(),
      role: "user",
      content: message,
      branchId: selectedBranchId,
      timestamp: new Date().toISOString(),
      metadata: {},
    })
  }

  // Final job cleanup
  useEffect(() => {
    const entries = Object.entries(jobs)
    for (const [jobId, job] of entries) {
      const msgId = jobToMsg[jobId]
      if (msgId && job.isCompleted) {
        import('@etherion/lib/services/goal-service').then(async ({ GoalService }) => {
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
    <div className={styles.container}>
      <div className={cx(styles.sidebar, timelineCollapsed ? "w-16" : "w-80")} style={{ display: 'none' }}>
        <ThreadList threads={threads} activeThreadId={activeThreadId} onThreadSelect={setActiveThreadId} />
      </div>

      <Drawer open={sidebarOpen} onClose={() => setSidebarOpen(false)} placement="left" width={280}>
        <ThreadList threads={threads} activeThreadId={activeThreadId} onThreadSelect={(id) => { setActiveThreadId(id); setSidebarOpen(false); }} />
      </Drawer>

      <div className={styles.mainArea}>
        <Flexbox className={styles.header} direction="horizontal" align="center" justify="space-between">
          <Space>
            <Button.Group>
              <Button type={planMode ? 'primary' : 'default'} onClick={() => setPlanMode(true)}>Plan</Button>
              <Button type={!planMode ? 'primary' : 'default'} onClick={() => setPlanMode(false)}>Act</Button>
            </Button.Group>
            <Button type={searchForce ? 'primary' : 'default'} onClick={() => toggleSearchForce(activeThreadId)}>
              Search: {searchForce ? 'On' : 'Off'}
            </Button>
            {mode === 'foundry' ? (
              <Button type="text" style={{ cursor: 'default' }}>
                Foundry (IO)
              </Button>
            ) : (
              <Select
                value={selectedTeamId}
                onSelect={setSelectedTeamId}
                style={{ minWidth: 160 }}
                options={teams.map(t => ({ value: t.id, label: t.name }))}
              />
            )}
          </Space>
          {(currentPrefs.provider || currentPrefs.model) && (
            <Tag color="processing">{currentPrefs.provider} • {currentPrefs.model}</Tag>
          )}
        </Flexbox>

        {Object.entries(jobs).filter(([_, j]) => !j.isCompleted && !j.isFailed).length > 0 && (
          <div className="p-4 bg-orange-500/10">
            <Space direction="vertical" className="w-full">
              {Object.entries(jobs)
                .filter(([_, j]) => !j.isCompleted && !j.isFailed)
                .map(([jobId]) => (
                  <JobStatusTracker key={jobId} jobId={jobId} onClose={() => removeJob(jobId)} />
                ))}
            </Space>
          </div>
        )}

        <div className={styles.scrollArea}>
          <div className="max-w-4xl mx-auto space-y-6">
            {messagesFromStore.map((m) => {
              const job = m.metadata?.toolExecId ? jobs[m.metadata.toolExecId] : undefined
              const statusChip = job ? (job.isCompleted ? 'Completed' : job.isFailed ? 'Failed' : 'Running') : undefined

              return (
                <MessageBubble
                  key={m.id}
                  statusChip={statusChip}
                  message={{
                    id: m.id,
                    role: m.role as any,
                    content: m.content,
                    timestamp: new Date(m.timestamp),
                    metadata: m.metadata as any
                  }}
                  threadId={activeThreadId}
                  branchId={selectedBranchId}
                  forkIndicator={forkStartIds.has(m.id)}
                  onToggleCot={() => toggleCot(activeThreadId, m.id)}
                  onToggleArtifacts={() => toggleArtifacts(activeThreadId, m.id)}
                  onApproveTool={(p) => runTool(p)}
                />
              )
            })}

            {Object.entries(jobs)
              .filter(([_, job]) => job.threadId === activeThreadId && !job.isCompleted && !job.isFailed)
              .map(([jobId]) => (
                <Flexbox key={jobId} gap={16}>
                  <ExecutionTraceUI jobId={jobId} />
                  <AgentBlueprintUI jobId={jobId} />
                </Flexbox>
              ))}
          </div>
        </div>

        <div className={styles.inputWrapper}>
          <div className="max-w-4xl mx-auto">
            <GoalInputBar
              onSubmit={handleSendMessage}
              threadId={activeThreadId}
              branchId={selectedBranchId}
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
