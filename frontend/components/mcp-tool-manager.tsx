"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Switch } from "@/components/ui/switch"
import { Slider } from "@/components/ui/slider"
import { Progress } from "@/components/ui/progress"
import {
  Wrench,
  Settings,
  Play,
  Pause,
  RotateCcw,
  BarChart3,
  Activity,
  Shield,
  Key,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  Zap,
  Database,
  Globe,
  Users,
  TrendingUp,
  RefreshCw,
  Plus,
  Edit,
  Trash2,
  Eye,
  EyeOff,
  Download,
  Upload
} from "lucide-react"
import { useApolloClient } from "@/components/apollo-provider";
import { useAuthStore } from "@/lib/stores/auth-store";
import { decodeJwt } from "@/lib/jwt";
import { useThreadPrefStore } from "@/lib/stores/thread-pref-store";
import { useTeamStore } from "@/lib/stores/team-store";
import { CredentialManager } from "./credential-manager";
import {
  GET_AVAILABLE_MCP_TOOLS_QUERY,
  EXECUTE_MCP_TOOL_MUTATION,
  TEST_MCP_TOOL_MUTATION,
  MANAGE_MCP_CREDENTIALS_MUTATION
} from "@/lib/graphql-operations"

interface MCPTool {
  id: string
  name: string
  description: string
  category: string
  status: 'active' | 'inactive' | 'error' | 'maintenance'
  version: string
  capabilities: string[]
  requiredCredentials: string[]
  maxConcurrentCalls: number
  rateLimit: number
  healthScore: number
  lastUsed: string | null
  totalExecutions: number
  successRate: number
  averageExecutionTime: number
  totalCost: number
  isEnabled: boolean
}

interface ToolMetrics {
  toolName: string
  executions: {
    timestamp: string
    success: boolean
    executionTime: number
    cost: number
  }[]
  healthMetrics: {
    uptime: number
    errorRate: number
    averageResponseTime: number
    throughput: number
  }
}

export function MCPToolManager({ preselectToolName, onClose }: { preselectToolName?: string; onClose?: () => void }) {
  const [tools, setTools] = useState<MCPTool[]>([])
  const [selectedTool, setSelectedTool] = useState<MCPTool | null>(null)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState<string | null>(null)
  const [executing, setExecuting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [toolMetrics, setToolMetrics] = useState<Record<string, ToolMetrics>>({})
  const client = useApolloClient();
  // Tool configuration states
  const [maxConcurrentCalls, setMaxConcurrentCalls] = useState([10])
  const [rateLimit, setRateLimit] = useState([100])
  const [isEnabled, setIsEnabled] = useState(true)

  // Execution parameters
  const [executionParams, setExecutionParams] = useState<Record<string, any>>({})
  const [executionResults, setExecutionResults] = useState<any[]>([])
  const [credModalOpen, setCredModalOpen] = useState(false)
  const { token } = useAuthStore()
  // ThreadView defaults to threadId "default"; use its Search toggle if available
  const searchForce = useThreadPrefStore((s) => s.searchForce['default'] || false)
  const selectedTeamId = useTeamStore((s) => s.selectedTeamId || undefined)

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
    loadAvailableTools()
  }, [])

  const loadAvailableTools = async () => {
    try {
      setLoading(true)
      const { data } = await client.query({
        query: GET_AVAILABLE_MCP_TOOLS_QUERY
      })

      const formattedTools = (data as any).getAvailableMCPTools.map((tool: any) => ({
        id: tool.name,
        name: tool.name,
        description: tool.description,
        category: tool.category || 'general',
        status: tool.status === 'STABLE' ? 'active' : tool.status === 'BETA' ? 'active' : 'inactive',
        version: tool.version || '1.0.0',
        capabilities: tool.capabilities || [],
        requiredCredentials: tool.requiredCredentials || [],
        maxConcurrentCalls: tool.maxConcurrentCalls || 10,
        rateLimit: tool.rateLimit || 100,
        healthScore: Math.floor(Math.random() * 100), // Mock health score
        lastUsed: new Date(Date.now() - Math.random() * 86400000).toISOString(), // Mock last used
        totalExecutions: Math.floor(Math.random() * 1000),
        successRate: 85 + Math.random() * 15,
        averageExecutionTime: 100 + Math.random() * 900,
        totalCost: Math.random() * 100,
        isEnabled: tool.status !== 'DEPRECATED'
      }))

      setTools(formattedTools)
      // Preselect tool when requested
      if (preselectToolName) {
        const found = formattedTools.find((t: MCPTool) => t.name === preselectToolName)
        if (found) setSelectedTool(found)
      }
    } catch (error) {
      console.error('Failed to load MCP tools:', error)
      setError('Failed to load available MCP tools')
    } finally {
      setLoading(false)
    }
  }

  const handleTestTool = async (toolName: string) => {
    try {
      setTesting(toolName)
      setError(null)

      const { data } = await client.mutate({
        mutation: TEST_MCP_TOOL_MUTATION,
        variables: { tool_name: toolName }
      })

      const result = (data as any).testMCPTool

      if (result.success) {
        setSuccess(`${toolName} is working correctly`)
        // Update tool status
        setTools(prev => prev.map(tool =>
          tool.name === toolName
            ? { ...tool, status: 'active', healthScore: Math.min(100, tool.healthScore + 10) }
            : tool
        ))
      } else {
        setError(`${toolName} test failed: ${result.errorMessage}`)
      }
    } catch (error) {
      console.error(`Failed to test ${toolName}:`, error)
      setError(`Failed to test ${toolName}`)
    } finally {
      setTesting(null)
    }
  }

  const handleExecuteTool = async (toolName: string, params: Record<string, any>) => {
    try {
      setExecuting(toolName)
      setError(null)
      const tenantId = getTenantId()
      if (!tenantId) {
        setError('Missing tenant identity')
        setExecuting(null)
        return
      }
      const { data } = await client.mutate({
        mutation: EXECUTE_MCP_TOOL_MUTATION,
        variables: {
          tool_name: toolName,
          params: JSON.stringify({
            tenant_id: tenantId,
            search_force: !!searchForce,
            ...(selectedTeamId ? { agent_team_id: selectedTeamId } : {}),
            ...params
          })
        }
      })

      const result = (data as any).executeMCPTool

      // Add to execution results
      const newResult = {
        toolName,
        timestamp: new Date().toISOString(),
        success: result.success,
        executionTime: result.executionTime,
        cost: result.cost,
        result: result.result,
        errorMessage: result.errorMessage
      }

      setExecutionResults(prev => [newResult, ...prev.slice(0, 9)]) // Keep last 10 results

      // Update tool metrics
      setTools(prev => prev.map(tool =>
        tool.name === toolName
          ? {
              ...tool,
              totalExecutions: tool.totalExecutions + 1,
              lastUsed: new Date().toISOString(),
              successRate: result.success
                ? Math.min(100, tool.successRate + 0.1)
                : Math.max(0, tool.successRate - 1),
              averageExecutionTime: (tool.averageExecutionTime * tool.totalExecutions + result.executionTime) / (tool.totalExecutions + 1)
            }
          : tool
      ))

      if (result.success) {
        setSuccess(`${toolName} executed successfully in ${result.executionTime}ms`)
      } else {
        setError(`${toolName} execution failed: ${result.errorMessage}`)
      }
    } catch (error) {
      console.error(`Failed to execute ${toolName}:`, error)
      setError(`Failed to execute ${toolName}`)
    } finally {
      setExecuting(null)
    }
  }

  const handleToggleTool = async (toolName: string, enabled: boolean) => {
    try {
      // Update local state immediately for responsive UI
      setTools(prev => prev.map(tool =>
        tool.name === toolName
          ? { ...tool, isEnabled: enabled, status: enabled ? 'active' : 'inactive' }
          : tool
      ))

      // TODO: Implement backend call to enable/disable tool
      console.log(`${enabled ? 'Enabling' : 'Disabling'} tool: ${toolName}`)

      setSuccess(`${toolName} ${enabled ? 'enabled' : 'disabled'} successfully`)
    } catch (error) {
      console.error(`Failed to toggle ${toolName}:`, error)
      setError(`Failed to toggle ${toolName}`)
      // Revert optimistic update
      setTools(prev => prev.map(tool =>
        tool.name === toolName
          ? { ...tool, isEnabled: !enabled, status: !enabled ? 'active' : 'inactive' }
          : tool
      ))
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500'
      case 'inactive': return 'bg-gray-500'
      case 'error': return 'bg-red-500'
      case 'maintenance': return 'bg-yellow-500'
      default: return 'bg-gray-500'
    }
  }

  const getHealthColor = (health: number) => {
    if (health >= 80) return 'text-green-600'
    if (health >= 60) return 'text-yellow-600'
    return 'text-red-600'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <RefreshCw className="h-8 w-8 animate-spin" />
        <span className="ml-2">Loading MCP tools...</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">MCP Tool Manager</h1>
          <p className="text-muted-foreground">Manage and monitor all MCP tools and integrations</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadAvailableTools}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Add Custom Tool
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert>
          <CheckCircle className="h-4 w-4" />
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Tool List */}
        <div className="lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Wrench className="h-5 w-5" />
                Available Tools ({tools.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {tools.map((tool) => (
                <div
                  key={tool.id}
                  className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedTool?.id === tool.id
                      ? 'bg-primary/10 border-primary'
                      : 'hover:bg-muted/50'
                  }`}
                  onClick={() => setSelectedTool(tool)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{tool.name}</span>
                        <Badge variant="outline" className="text-xs">
                          v{tool.version}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground truncate">
                        {tool.description}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <div className={`w-2 h-2 rounded-full ${getStatusColor(tool.status)}`} />
                        <span className="text-xs text-muted-foreground">{tool.status}</span>
                        <span className={`text-xs font-medium ${getHealthColor(tool.healthScore)}`}>
                          {tool.healthScore}% healthy
                        </span>
                      </div>
                    </div>
                    <Switch
                      checked={tool.isEnabled}
                      onCheckedChange={(checked) => handleToggleTool(tool.name, checked)}
                      disabled={testing === tool.name || executing === tool.name}
                    />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Tool Details */}
        <div className="lg:col-span-2">
          {selectedTool ? (
            <>
            <Tabs defaultValue="overview" className="space-y-4">
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="configuration">Configuration</TabsTrigger>
                <TabsTrigger value="testing">Testing</TabsTrigger>
                <TabsTrigger value="analytics">Analytics</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Settings className="h-5 w-5" />
                      {selectedTool.name} Overview
                    </CardTitle>
                    <CardDescription>{selectedTool.description}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="text-center">
                        <div className="text-2xl font-bold">{selectedTool.totalExecutions}</div>
                        <div className="text-sm text-muted-foreground">Total Executions</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold">{selectedTool.successRate.toFixed(1)}%</div>
                        <div className="text-sm text-muted-foreground">Success Rate</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold">{selectedTool.averageExecutionTime.toFixed(0)}ms</div>
                        <div className="text-sm text-muted-foreground">Avg Response</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold">${selectedTool.totalCost.toFixed(2)}</div>
                        <div className="text-sm text-muted-foreground">Total Cost</div>
                      </div>
                    </div>

                    <div>
                      <h4 className="font-medium mb-2">Capabilities</h4>
                      <div className="flex flex-wrap gap-1">
                        {selectedTool.capabilities.map((capability, index) => (
                          <Badge key={index} variant="secondary">
                            {capability.replace(/_/g, ' ')}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h4 className="font-medium mb-2">Required Credentials</h4>
                      <div className="flex flex-wrap gap-1">
                        {selectedTool.requiredCredentials.map((credential, index) => (
                          <Badge key={index} variant="outline">
                            <Key className="mr-1 h-3 w-3" />
                            {credential}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                  <CardFooter className="flex gap-2">
                    <Button
                      onClick={() => handleTestTool(selectedTool.name)}
                      disabled={testing === selectedTool.name || !selectedTool.isEnabled}
                    >
                      {testing === selectedTool.name ? (
                        <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Activity className="mr-2 h-4 w-4" />
                      )}
                      Test Tool
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setCredModalOpen(true)}
                    >
                      <Key className="mr-2 h-4 w-4" />
                      Configure Credentials
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => handleExecuteTool(selectedTool.name, executionParams)}
                      disabled={executing === selectedTool.name || !selectedTool.isEnabled}
                    >
                      {executing === selectedTool.name ? (
                        <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Play className="mr-2 h-4 w-4" />
                      )}
                      Execute Tool
                    </Button>
                  </CardFooter>
                </Card>
              </TabsContent>

              <TabsContent value="configuration" className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle>Tool Configuration</CardTitle>
                    <CardDescription>Adjust tool settings and limits</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="space-y-2">
                      <Label>Max Concurrent Calls: {maxConcurrentCalls[0]}</Label>
                      <Slider
                        value={maxConcurrentCalls}
                        onValueChange={setMaxConcurrentCalls}
                        max={100}
                        min={1}
                        step={1}
                        className="w-full"
                      />
                    </div>

                    <div className="space-y-2">
                      <Label>Rate Limit (calls per minute): {rateLimit[0]}</Label>
                      <Slider
                        value={rateLimit}
                        onValueChange={setRateLimit}
                        max={1000}
                        min={10}
                        step={10}
                        className="w-full"
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label>Tool Enabled</Label>
                        <div className="text-sm text-muted-foreground">
                          Allow this tool to be used in executions
                        </div>
                      </div>
                      <Switch
                        checked={isEnabled}
                        onCheckedChange={setIsEnabled}
                      />
                    </div>
                  </CardContent>
                  <CardFooter>
                    <Button className="w-full">
                      <Settings className="mr-2 h-4 w-4" />
                      Save Configuration
                    </Button>
                  </CardFooter>
                </Card>
              </TabsContent>

              <TabsContent value="testing" className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle>Test Tool Functionality</CardTitle>
                    <CardDescription>Test the tool with sample parameters</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-2">
                      <Label>Test Parameters (JSON)</Label>
                      <Textarea
                        placeholder='{"action": "test", "parameter": "value"}'
                        value={JSON.stringify(executionParams, null, 2)}
                        onChange={(e) => {
                          try {
                            const parsed = JSON.parse(e.target.value)
                            setExecutionParams(parsed)
                          } catch (error) {
                            // Invalid JSON, keep current value
                          }
                        }}
                        rows={6}
                      />
                    </div>
                  </CardContent>
                  <CardFooter>
                    <Button
                      className="w-full"
                      onClick={() => handleExecuteTool(selectedTool.name, executionParams)}
                      disabled={executing === selectedTool.name}
                    >
                      {executing === selectedTool.name ? (
                        <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Play className="mr-2 h-4 w-4" />
                      )}
                      Execute Test
                    </Button>
                  </CardFooter>
                </Card>

                {executionResults.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Recent Executions</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {executionResults.slice(0, 5).map((result, index) => (
                          <div key={index} className="p-3 border rounded-lg">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                {result.success ? (
                                  <CheckCircle className="h-4 w-4 text-green-600" />
                                ) : (
                                  <XCircle className="h-4 w-4 text-red-600" />
                                )}
                                <span className="text-sm font-medium">{result.toolName}</span>
                                <span className="text-xs text-muted-foreground">
                                  {new Date(result.timestamp).toLocaleTimeString()}
                                </span>
                              </div>
                              <div className="text-right">
                                <div className="text-sm">{result.executionTime}ms</div>
                                <div className="text-xs text-muted-foreground">
                                  ${result.cost?.toFixed(4) || '0.0000'}
                                </div>
                              </div>
                            </div>
                            {!result.success && result.errorMessage && (
                              <div className="mt-2 text-sm text-red-600">
                                {result.errorMessage}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </TabsContent>

              <TabsContent value="analytics" className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <BarChart3 className="h-5 w-5" />
                        Performance Metrics
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div>
                        <div className="flex justify-between text-sm">
                          <span>Health Score</span>
                          <span className={getHealthColor(selectedTool.healthScore)}>
                            {selectedTool.healthScore}%
                          </span>
                        </div>
                        <Progress value={selectedTool.healthScore} className="mt-1" />
                      </div>

                      <div>
                        <div className="flex justify-between text-sm">
                          <span>Success Rate</span>
                          <span>{selectedTool.successRate.toFixed(1)}%</span>
                        </div>
                        <Progress value={selectedTool.successRate} className="mt-1" />
                      </div>

                      <div className="grid grid-cols-2 gap-4 pt-2">
                        <div className="text-center">
                          <div className="text-lg font-semibold">{selectedTool.totalExecutions}</div>
                          <div className="text-xs text-muted-foreground">Total Calls</div>
                        </div>
                        <div className="text-center">
                          <div className="text-lg font-semibold">{selectedTool.averageExecutionTime.toFixed(0)}ms</div>
                          <div className="text-xs text-muted-foreground">Avg Response</div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <TrendingUp className="h-5 w-5" />
                        Usage Trends
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <div className="flex justify-between">
                          <span className="text-sm">Last Used</span>
                          <span className="text-sm text-muted-foreground">
                            {selectedTool.lastUsed
                              ? new Date(selectedTool.lastUsed).toLocaleString()
                              : 'Never'
                            }
                          </span>
                        </div>

                        <div className="flex justify-between">
                          <span className="text-sm">Total Cost</span>
                          <span className="text-sm font-medium">
                            ${selectedTool.totalCost.toFixed(4)}
                          </span>
                        </div>

                        <div className="flex justify-between">
                          <span className="text-sm">Category</span>
                          <Badge variant="outline">{selectedTool.category}</Badge>
                        </div>

                        <div className="flex justify-between">
                          <span className="text-sm">Version</span>
                          <span className="text-sm">{selectedTool.version}</span>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>
            </Tabs>
            {/* Credentials Modal */}
            <Dialog open={credModalOpen} onOpenChange={setCredModalOpen}>
              <DialogContent className="max-w-3xl">
                <DialogHeader>
                  <DialogTitle>Configure Credentials</DialogTitle>
                </DialogHeader>
                {selectedTool && (
                  <CredentialManager toolName={selectedTool.name} onClose={() => setCredModalOpen(false)} />
                )}
                <DialogFooter>
                  <Button variant="outline" onClick={() => setCredModalOpen(false)}>Close</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
            </>
          ) : (
            <Card>
              <CardContent className="flex items-center justify-center p-8">
                <div className="text-center">
                  <Wrench className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <h3 className="text-lg font-medium mb-2">No Tool Selected</h3>
                  <p className="text-muted-foreground">
                    Select an MCP tool from the list to view its details and manage its configuration.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
