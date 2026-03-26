"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Edit, Trash2, Bot, Plus } from "lucide-react"
import { useApolloClient } from "@/components/apollo-provider";
import { useAuthStore } from "@/lib/stores/auth-store";
import { decodeJwt } from "@/lib/jwt";
import { GET_AGENTS_QUERY, CREATE_AGENT_MUTATION, UPDATE_AGENT_MUTATION, DELETE_AGENT_MUTATION } from "@/lib/graphql-operations"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"

interface Agent {
  id: string
  name: string
  description: string
  createdAt: string
  lastUsed?: string
  status: string
  agentType: string
  capabilities: string[]
  performanceMetrics?: {
    successRate?: number
    averageExecutionTime?: number
    totalExecutions?: number
  }
}

interface AgentInput {
  name: string
  description: string
  agentType: string
  capabilities: string[]
  systemPrompt?: string
}

interface AgentCardProps {
  agent: Agent
  onEdit: (agent: Agent) => void
  onDelete: (agent: Agent) => void
}

function AgentCard({ agent, onEdit, onDelete }: AgentCardProps) {
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString()
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "active":
        return "bg-green-500"
      case "inactive":
        return "bg-gray-400"
      case "training":
        return "bg-yellow-500"
      default:
        return "bg-gray-400"
    }
  }

  

  

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <Bot className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base">{agent.name}</CardTitle>
              <div className="flex items-center gap-2 mt-1">
                <div className={`w-2 h-2 rounded-full ${getStatusColor(agent.status)}`} />
                <span className="text-xs text-muted-foreground capitalize">{agent.status}</span>
                <span className="text-xs text-muted-foreground">•</span>
                <span className="text-xs text-muted-foreground capitalize">{agent.agentType}</span>
              </div>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <CardDescription className="text-sm leading-relaxed">{agent.description}</CardDescription>

        {agent.capabilities && agent.capabilities.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {agent.capabilities.slice(0, 3).map((capability: string, index: number) => (
              <span
                key={index}
                className="text-xs px-2 py-1 bg-secondary rounded-md text-secondary-foreground"
              >
                {capability}
              </span>
            ))}
            {agent.capabilities.length > 3 && (
              <span className="text-xs px-2 py-1 bg-secondary rounded-md text-secondary-foreground">
                +{agent.capabilities.length - 3} more
              </span>
            )}
          </div>
        )}

        <div className="text-xs text-muted-foreground space-y-1">
          <div>Created: {formatDate(agent.createdAt)}</div>
          {agent.lastUsed && <div>Last used: {formatDate(agent.lastUsed)}</div>}
        </div>

        {agent.performanceMetrics && (
          <div className="text-xs text-muted-foreground space-y-1 pt-2 border-t">
            {agent.performanceMetrics.successRate !== undefined && (
              <div>Success Rate: {(agent.performanceMetrics.successRate * 100).toFixed(1)}%</div>
            )}
            {agent.performanceMetrics.totalExecutions !== undefined && (
              <div>Total Executions: {agent.performanceMetrics.totalExecutions}</div>
            )}
            {agent.performanceMetrics.averageExecutionTime !== undefined && (
              <div>Avg Time: {agent.performanceMetrics.averageExecutionTime.toFixed(1)}s</div>
            )}
          </div>
        )}
      </CardContent>
      <CardFooter className="flex gap-2">
        <Button variant="outline" size="sm" className="flex-1 gap-2 bg-transparent" onClick={() => onEdit(agent)}>
          <Edit className="h-4 w-4" />
          Edit
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="flex-1 gap-2 text-destructive hover:text-destructive bg-transparent"
          onClick={() => onDelete(agent)}
        >
          <Trash2 className="h-4 w-4" />
          Delete
        </Button>
      </CardFooter>
    </Card>
  )
}

export function AgentRegistry() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const client = useApolloClient();
  const { token } = useAuthStore();
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<Agent | null>(null)
  const [form, setForm] = useState<AgentInput>({ name: "", description: "", agentType: "", capabilities: [], systemPrompt: "" })
  const [capabilitiesText, setCapabilitiesText] = useState("")

  const getTenantId = (): number | null => {
    try {
      const t = token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null);
      if (!t) return null;
      const payload = decodeJwt(t);
      const tid = (payload && ((payload as any).tenant_id ?? (payload as any).tenantId)) as number | string | undefined;
      if (!tid) return null;
      const n = Number(tid);
      return Number.isFinite(n) ? n : null;
    } catch {
      return null;
    }
  }
  useEffect(() => {
    fetchAgents()
  }, [])

  const fetchAgents = async () => {
    try {
      setLoading(true)
      setError(null)
      const tenantId = getTenantId();
      if (!tenantId) {
        throw new Error('Missing tenant identity');
      }
      const { data } = await client.query({
        query: GET_AGENTS_QUERY,
        variables: { tenant_id: tenantId }
      })

      setAgents(data.getAgents)
    } catch (error) {
      console.error('Failed to fetch agents:', error)
      setError('Failed to load agents')
    } finally {
      setLoading(false)
    }
  }

  const handleEdit = (agent: Agent) => {
    setEditing(agent)
    setForm({
      name: agent.name || "",
      description: agent.description || "",
      agentType: agent.agentType || "",
      capabilities: agent.capabilities || [],
      systemPrompt: form.systemPrompt || "",
    })
    setCapabilitiesText((agent.capabilities || []).join(", "))
    setEditOpen(true)
  }

  const handleDelete = async (agent: Agent) => {
    try {
      await client.mutate({
        mutation: DELETE_AGENT_MUTATION,
        variables: { agent_id: agent.id }
      })

      // Update local state
      setAgents((prev) => prev.filter((a) => a.id !== agent.id))
      console.log("Agent deleted successfully:", agent.name)
    } catch (error) {
      console.error('Failed to delete agent:', error)
      setError('Failed to delete agent')
    }
  }

  const handleCreateAgent = async (agentInput: AgentInput) => {
    try {
      const { data } = await client.mutate({
        mutation: CREATE_AGENT_MUTATION,
        variables: { agent_input: agentInput }
      })

      // Update local state with new agent
      setAgents([...agents, data.createAgent])
      console.log("Agent created successfully:", data.createAgent.name)
    } catch (error) {
      console.error('Failed to create agent:', error)
      setError('Failed to create agent')
    }
  }

  // Persist edits and update local list
  const submitEdit = async () => {
    if (!editing) return
    try {
      const payload: AgentInput = {
        ...form,
        capabilities: (capabilitiesText || "")
          .split(',')
          .map((s: string) => s.trim())
          .filter((s: string) => s.length > 0),
      }

      const { data } = await client.mutate({
        mutation: UPDATE_AGENT_MUTATION,
        variables: { agent_id: editing.id, agent_input: payload },
      })

      const updated = data?.updateAgent
      if (updated) {
        setAgents((prev) =>
          prev.map((a) =>
            a.id === updated.id
              ? {
                  ...a,
                  name: updated.name,
                  description: updated.description,
                  status: updated.status,
                  agentType: payload.agentType,
                  capabilities: payload.capabilities,
                }
              : a,
          ),
        )
      }
      setEditOpen(false)
      setEditing(null)
    } catch (e) {
      console.error('Failed to update agent:', e)
      setError('Failed to update agent')
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Agent Registry</h1>
            <p className="text-muted-foreground">Manage your custom AI agents and their configurations</p>
          </div>
        </div>
        <div className="flex items-center justify-center py-12">
          <div className="text-muted-foreground">Loading agents...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Agent Registry</h1>
            <p className="text-muted-foreground">Manage your custom AI agents and their configurations</p>
          </div>
        </div>
        <Card className="text-center py-12">
          <CardContent>
            <div className="text-destructive mb-4">{error}</div>
            <Button onClick={fetchAgents} variant="outline">
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Agent Registry</h1>
          <p className="text-muted-foreground">Manage your custom AI agents and their configurations</p>
        </div>
        <Button
          className="gap-2"
          onClick={() => {
            // TODO: Open create agent modal
            console.log("Create new agent clicked")
          }}
        >
          <Plus className="h-4 w-4" />
          Create New Agent
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {agents.map((agent) => (
          <AgentCard key={agent.id} agent={agent} onEdit={handleEdit} onDelete={handleDelete} />
        ))}
      </div>

      {agents.length === 0 && (
        <Card className="text-center py-12">
          <CardContent>
            <Bot className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium mb-2">No agents created yet</h3>
            <p className="text-muted-foreground mb-4">Create your first AI agent to get started</p>
            <Button
              className="gap-2"
              onClick={() => {
                // TODO: Open create agent modal
                console.log("Create new agent clicked")
              }}
            >
              <Plus className="h-4 w-4" />
              Create New Agent
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Edit Agent Modal */}
      <Dialog open={editOpen} onOpenChange={(open) => { setEditOpen(open); if (!open) setEditing(null) }}>
        <DialogContent className="glass-strong border-border">
          <DialogHeader>
            <DialogTitle>Edit Agent</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="agent-name">Name</Label>
              <Input id="agent-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-desc">Description</Label>
              <Textarea id="agent-desc" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-type">Agent Type</Label>
              <Input id="agent-type" value={form.agentType} onChange={(e) => setForm({ ...form, agentType: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-capabilities">Capabilities (comma-separated)</Label>
              <Input id="agent-capabilities" value={capabilitiesText} onChange={(e) => setCapabilitiesText(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-system-prompt">System Prompt (optional)</Label>
              <Textarea id="agent-system-prompt" rows={4} value={form.systemPrompt || ""} onChange={(e) => setForm({ ...form, systemPrompt: e.target.value })} />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditOpen(false); setEditing(null) }}>Cancel</Button>
            <Button onClick={submitEdit}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
