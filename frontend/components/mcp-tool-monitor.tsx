"use client"

import { useState, useEffect, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Clock,
  Zap,
  Database,
  Globe,
  Users,
  BarChart3,
  Server,
  Wifi,
  WifiOff,
  Shield,
  Gauge
} from "lucide-react"
import { useApolloClient } from "@/components/apollo-provider";
import { GET_AVAILABLE_MCP_TOOLS_QUERY, TEST_MCP_TOOL_MUTATION } from "@/lib/graphql-operations"
// TODO(step4): Replace mock health with real telemetry from server metrics GraphQL (latency, error rate, uptime, throughput)

interface ToolHealth {
  toolName: string
  status: 'healthy' | 'degraded' | 'down' | 'unknown'
  responseTime: number
  uptime: number
  errorRate: number
  throughput: number
  lastCheck: string
  consecutiveFailures: number
  totalRequests: number
  successfulRequests: number
}

interface SystemMetrics {
  totalTools: number
  activeTools: number
  healthyTools: number
  degradedTools: number
  downTools: number
  averageResponseTime: number
  totalThroughput: number
  errorRate: number
  uptime: number
}

export function MCPToolMonitor() {
  const [tools, setTools] = useState<ToolHealth[]>([])
  const [systemMetrics, setSystemMetrics] = useState<SystemMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshInterval, setRefreshInterval] = useState(30) // seconds
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())
  const [selectedTimeRange, setSelectedTimeRange] = useState("5m")
  const client = useApolloClient();
  const loadToolHealth = useCallback(async () => {
    try {
      setLoading(true)
      const { data } = await client.query({
        query: GET_AVAILABLE_MCP_TOOLS_QUERY
      })

      // Mock health data - in real implementation, this would come from monitoring service
      const mockHealthData: ToolHealth[] = (data as any).getAvailableMCPTools.map((tool: any, index: number) => {
        const baseResponseTime = 100 + Math.random() * 400
        const uptime = 95 + Math.random() * 5
        const errorRate = Math.random() * 5
        const throughput = Math.floor(Math.random() * 1000) + 50

        let status: 'healthy' | 'degraded' | 'down' | 'unknown' = 'healthy'
        if (errorRate > 3) status = 'degraded'
        if (errorRate > 10 || uptime < 90) status = 'down'

        return {
          toolName: tool.name,
          status,
          responseTime: baseResponseTime,
          uptime,
          errorRate,
          throughput,
          lastCheck: new Date().toISOString(),
          consecutiveFailures: status === 'down' ? Math.floor(Math.random() * 10) + 1 : 0,
          totalRequests: Math.floor(Math.random() * 10000) + 1000,
          successfulRequests: Math.floor(Math.random() * 9500) + 500
        }
      })

      setTools(mockHealthData)

      // Calculate system metrics
      const healthy = mockHealthData.filter(t => t.status === 'healthy').length
      const degraded = mockHealthData.filter(t => t.status === 'degraded').length
      const down = mockHealthData.filter(t => t.status === 'down').length
      const active = healthy + degraded

      const avgResponseTime = mockHealthData.reduce((sum, t) => sum + t.responseTime, 0) / mockHealthData.length
      const totalThroughput = mockHealthData.reduce((sum, t) => sum + t.throughput, 0)
      const avgErrorRate = mockHealthData.reduce((sum, t) => sum + t.errorRate, 0) / mockHealthData.length
      const avgUptime = mockHealthData.reduce((sum, t) => sum + t.uptime, 0) / mockHealthData.length

      setSystemMetrics({
        totalTools: mockHealthData.length,
        activeTools: active,
        healthyTools: healthy,
        degradedTools: degraded,
        downTools: down,
        averageResponseTime: avgResponseTime,
        totalThroughput,
        errorRate: avgErrorRate,
        uptime: avgUptime
      })

      setLastRefresh(new Date())
    } catch (error) {
      console.error('Failed to load tool health:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadToolHealth()
  }, [loadToolHealth])

  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(() => {
      loadToolHealth()
    }, refreshInterval * 1000)

    return () => clearInterval(interval)
  }, [autoRefresh, refreshInterval, loadToolHealth])

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-green-600'
      case 'degraded': return 'text-yellow-600'
      case 'down': return 'text-red-600'
      default: return 'text-gray-600'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy': return <CheckCircle className="h-4 w-4 text-green-600" />
      case 'degraded': return <AlertTriangle className="h-4 w-4 text-yellow-600" />
      case 'down': return <XCircle className="h-4 w-4 text-red-600" />
      default: return <Activity className="h-4 w-4 text-gray-600" />
    }
  }

  const formatUptime = (uptime: number) => {
    return `${uptime.toFixed(2)}%`
  }

  const formatResponseTime = (time: number) => {
    return `${time.toFixed(0)}ms`
  }

  const formatThroughput = (throughput: number) => {
    if (throughput >= 1000) {
      return `${(throughput / 1000).toFixed(1)}k/min`
    }
    return `${throughput}/min`
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <RefreshCw className="h-8 w-8 animate-spin" />
        <span className="ml-2">Loading tool health data...</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">MCP Tool Monitor</h1>
          <p className="text-muted-foreground">Real-time monitoring and health status of all MCP tools</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            Last updated: {lastRefresh.toLocaleTimeString()}
          </span>
          <Button variant="outline" size="sm" onClick={loadToolHealth}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button
            variant={autoRefresh ? "default" : "outline"}
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? "Auto-refresh ON" : "Auto-refresh OFF"}
          </Button>
        </div>
      </div>

      {systemMetrics && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Tools</p>
                  <p className="text-2xl font-bold">{systemMetrics.totalTools}</p>
                </div>
                <Server className="h-8 w-8 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Healthy</p>
                  <p className="text-2xl font-bold text-green-600">{systemMetrics.healthyTools}</p>
                </div>
                <CheckCircle className="h-8 w-8 text-green-600" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Avg Response</p>
                  <p className="text-2xl font-bold">{formatResponseTime(systemMetrics.averageResponseTime)}</p>
                </div>
                <Zap className="h-8 w-8 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">System Uptime</p>
                  <p className="text-2xl font-bold">{formatUptime(systemMetrics.uptime)}</p>
                </div>
                <Gauge className="h-8 w-8 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="tools">Individual Tools</TabsTrigger>
          <TabsTrigger value="alerts">Alerts</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Tool Status Summary */}
            <Card>
              <CardHeader>
                <CardTitle>Tool Status Summary</CardTitle>
                <CardDescription>Current health status of all MCP tools</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {systemMetrics && (
                  <>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Healthy Tools</span>
                        <span className="text-sm font-medium text-green-600">
                          {systemMetrics.healthyTools} / {systemMetrics.totalTools}
                        </span>
                      </div>
                      <Progress
                        value={(systemMetrics.healthyTools / systemMetrics.totalTools) * 100}
                        className="h-2"
                      />
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Degraded Tools</span>
                        <span className="text-sm font-medium text-yellow-600">
                          {systemMetrics.degradedTools}
                        </span>
                      </div>
                      <Progress
                        value={(systemMetrics.degradedTools / systemMetrics.totalTools) * 100}
                        className="h-2"
                      />
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm">Down Tools</span>
                        <span className="text-sm font-medium text-red-600">
                          {systemMetrics.downTools}
                        </span>
                      </div>
                      <Progress
                        value={(systemMetrics.downTools / systemMetrics.totalTools) * 100}
                        className="h-2"
                      />
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* System Performance */}
            <Card>
              <CardHeader>
                <CardTitle>System Performance</CardTitle>
                <CardDescription>Overall system metrics and performance indicators</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="text-center">
                    <div className="text-lg font-semibold">
                      {formatResponseTime(systemMetrics?.averageResponseTime || 0)}
                    </div>
                    <div className="text-xs text-muted-foreground">Avg Response Time</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-semibold">
                      {formatThroughput(systemMetrics?.totalThroughput || 0)}
                    </div>
                    <div className="text-xs text-muted-foreground">Total Throughput</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-semibold">
                      {(systemMetrics?.errorRate || 0).toFixed(2)}%
                    </div>
                    <div className="text-xs text-muted-foreground">Error Rate</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-semibold">
                      {formatUptime(systemMetrics?.uptime || 0)}
                    </div>
                    <div className="text-xs text-muted-foreground">System Uptime</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Recent Activity */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>Latest events and status changes</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {tools.slice(0, 5).map((tool) => (
                  <div key={tool.toolName} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center gap-3">
                      {getStatusIcon(tool.status)}
                      <div>
                        <div className="font-medium">{tool.toolName}</div>
                        <div className="text-sm text-muted-foreground">
                          Status: {tool.status} • {formatUptime(tool.uptime)} uptime
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-medium">{formatResponseTime(tool.responseTime)}</div>
                      <div className="text-xs text-muted-foreground">
                        {formatThroughput(tool.throughput)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tools" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {tools.map((tool) => (
              <Card key={tool.toolName}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      {getStatusIcon(tool.status)}
                      {tool.toolName}
                    </CardTitle>
                    <Badge
                      variant={tool.status === 'healthy' ? 'default' : 'destructive'}
                      className={tool.status === 'healthy' ? 'bg-green-500' : ''}
                    >
                      {tool.status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="pt-0 space-y-3">
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Uptime</span>
                      <span className="font-medium">{formatUptime(tool.uptime)}</span>
                    </div>
                    <Progress value={tool.uptime} className="h-2" />
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Error Rate</span>
                      <span className="font-medium">{tool.errorRate.toFixed(2)}%</span>
                    </div>
                    <Progress value={tool.errorRate * 10} className="h-2" />
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="font-medium">{formatResponseTime(tool.responseTime)}</div>
                      <div className="text-muted-foreground">Response Time</div>
                    </div>
                    <div>
                      <div className="font-medium">{formatThroughput(tool.throughput)}</div>
                      <div className="text-muted-foreground">Throughput</div>
                    </div>
                  </div>

                  <div className="text-xs text-muted-foreground">
                    Last check: {new Date(tool.lastCheck).toLocaleTimeString()}
                  </div>
                </CardContent>
                <CardFooter className="pt-0">
                  <Button size="sm" className="w-full">
                    <Activity className="mr-2 h-4 w-4" />
                    View Details
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="alerts" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Active Alerts</CardTitle>
              <CardDescription>Issues requiring attention</CardDescription>
            </CardHeader>
            <CardContent>
              {tools.filter(tool => tool.status !== 'healthy').length === 0 ? (
                <div className="text-center py-8">
                  <CheckCircle className="h-12 w-12 text-green-600 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-green-600 mb-2">All Systems Operational</h3>
                  <p className="text-muted-foreground">No active alerts at this time.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {tools.filter(tool => tool.status !== 'healthy').map((tool) => (
                    <Alert key={tool.toolName} variant="destructive">
                      <AlertTriangle className="h-4 w-4" />
                      <AlertDescription>
                        <div className="flex items-center justify-between">
                          <div>
                            <strong>{tool.toolName}</strong> is {tool.status}
                            {tool.consecutiveFailures > 0 && (
                              <span className="ml-2">({tool.consecutiveFailures} consecutive failures)</span>
                            )}
                          </div>
                          <div className="text-sm">
                            Last check: {new Date(tool.lastCheck).toLocaleTimeString()}
                          </div>
                        </div>
                      </AlertDescription>
                    </Alert>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analytics" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Performance Trends</CardTitle>
                <CardDescription>Response time and throughput over time</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingUp className="h-4 w-4 text-green-600" />
                      <span className="text-sm font-medium">Response Time Trend</span>
                    </div>
                    <div className="text-2xl font-bold text-green-600">
                      {systemMetrics?.averageResponseTime ? formatResponseTime(systemMetrics.averageResponseTime) : '0ms'}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Average across all tools
                    </p>
                  </div>

                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Activity className="h-4 w-4 text-blue-600" />
                      <span className="text-sm font-medium">Throughput Trend</span>
                    </div>
                    <div className="text-2xl font-bold text-blue-600">
                      {systemMetrics?.totalThroughput ? formatThroughput(systemMetrics.totalThroughput) : '0/min'}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Total requests per minute
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Health Distribution</CardTitle>
                <CardDescription>Distribution of tool health statuses</CardDescription>
              </CardHeader>
              <CardContent>
                {systemMetrics && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 bg-green-500 rounded-full" />
                        <span className="text-sm">Healthy</span>
                      </div>
                      <span className="text-sm font-medium">{systemMetrics.healthyTools}</span>
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 bg-yellow-500 rounded-full" />
                        <span className="text-sm">Degraded</span>
                      </div>
                      <span className="text-sm font-medium">{systemMetrics.degradedTools}</span>
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 bg-red-500 rounded-full" />
                        <span className="text-sm">Down</span>
                      </div>
                      <span className="text-sm font-medium">{systemMetrics.downTools}</span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
