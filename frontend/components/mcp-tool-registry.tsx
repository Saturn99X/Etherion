"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Progress } from "@/components/ui/progress"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import {
  Wrench,
  Search,
  Filter,
  Grid3X3,
  List,
  Star,
  Download,
  Upload,
  Settings,
  Activity,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  TrendingUp,
  Zap,
  Database,
  Globe,
  Users,
  Key
} from "lucide-react"
import { useApolloClient } from "@/components/apollo-provider";
import { GET_AVAILABLE_MCP_TOOLS_QUERY } from "@/lib/graphql-operations"
import { MCPToolManager } from "./mcp-tool-manager"
import { CredentialManager } from "./credential-manager"

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
  tags: string[]
  author: string
  documentationUrl?: string
  lastUpdated: string
}

export function MCPToolRegistry() {
  const [tools, setTools] = useState<MCPTool[]>([])
  const [filteredTools, setFilteredTools] = useState<MCPTool[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [categoryFilter, setCategoryFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [sortBy, setSortBy] = useState("name")
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid")
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [managerOpen, setManagerOpen] = useState(false)
  const [credOpen, setCredOpen] = useState(false)
  const [selectedToolName, setSelectedToolName] = useState<string | null>(null)
  const client = useApolloClient();
  useEffect(() => {
    loadAvailableTools()
  }, [])

  useEffect(() => {
    filterAndSortTools()
  }, [tools, searchQuery, categoryFilter, statusFilter, sortBy])

  const loadAvailableTools = async () => {
    try {
      setLoading(true)
      const { data } = await client.query({
        query: GET_AVAILABLE_MCP_TOOLS_QUERY
      })

      const formattedTools = (data as any).getAvailableMCPTools.map((tool: any, index: number) => ({
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
        healthScore: Math.floor(Math.random() * 40) + 60, // Mock health score 60-100
        lastUsed: Math.random() > 0.3 ? new Date(Date.now() - Math.random() * 86400000 * 7).toISOString() : null,
        totalExecutions: Math.floor(Math.random() * 10000) + 100,
        successRate: 75 + Math.random() * 25, // 75-100%
        averageExecutionTime: 50 + Math.random() * 950, // 50-1000ms
        totalCost: Math.random() * 500 + 10, // $10-510
        isEnabled: tool.status !== 'DEPRECATED',
        tags: tool.tags || ['mcp', 'integration'],
        author: tool.author || 'System',
        documentationUrl: tool.documentationUrl,
        lastUpdated: new Date(Date.now() - Math.random() * 86400000 * 30).toISOString()
      }))

      setTools(formattedTools)
    } catch (error) {
      console.error('Failed to load MCP tools:', error)
    } finally {
      setLoading(false)
    }
  }

  const filterAndSortTools = () => {
    let filtered = tools.filter(tool => {
      const matchesSearch = tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                           tool.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
                           tool.capabilities.some(cap => cap.toLowerCase().includes(searchQuery.toLowerCase()))

      const matchesCategory = categoryFilter === "all" || tool.category === categoryFilter
      const matchesStatus = statusFilter === "all" || tool.status === statusFilter

      return matchesSearch && matchesCategory && matchesStatus
    })

    // Sort tools
    filtered.sort((a, b) => {
      switch (sortBy) {
        case "name":
          return a.name.localeCompare(b.name)
        case "category":
          return a.category.localeCompare(b.category)
        case "health":
          return b.healthScore - a.healthScore
        case "usage":
          return b.totalExecutions - a.totalExecutions
        case "success":
          return b.successRate - a.successRate
        case "lastUsed":
          if (!a.lastUsed) return 1
          if (!b.lastUsed) return -1
          return new Date(b.lastUsed).getTime() - new Date(a.lastUsed).getTime()
        default:
          return 0
      }
    })

    setFilteredTools(filtered)
  }

  const getCategories = () => {
    const categories = Array.from(new Set(tools.map(tool => tool.category)))
    return categories.sort()
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
    if (health >= 90) return 'text-green-600'
    if (health >= 70) return 'text-yellow-600'
    return 'text-red-600'
  }

  const formatLastUsed = (lastUsed: string | null) => {
    if (!lastUsed) return 'Never'
    const now = new Date()
    const last = new Date(lastUsed)
    const diffHours = Math.floor((now.getTime() - last.getTime()) / (1000 * 60 * 60))

    if (diffHours < 1) return 'Just now'
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffHours < 168) return `${Math.floor(diffHours / 24)}d ago`
    return last.toLocaleDateString()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
          <p>Loading MCP Tool Registry...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">MCP Tool Registry</h1>
          <p className="text-muted-foreground">Discover and manage all available MCP tools</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <Upload className="mr-2 h-4 w-4" />
            Import
          </Button>
          <Button variant="outline" size="sm">
            <Download className="mr-2 h-4 w-4" />
            Export
          </Button>
          <Button size="sm">
            <Star className="mr-2 h-4 w-4" />
            Featured
          </Button>
        </div>
      </div>

      {/* Filters and Search */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search tools, capabilities, or descriptions..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>

            <div className="flex gap-2">
              <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                <SelectTrigger className="w-40">
                  <Filter className="mr-2 h-4 w-4" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Categories</SelectItem>
                  {getCategories().map(category => (
                    <SelectItem key={category} value={category}>
                      {category}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                  <SelectItem value="maintenance">Maintenance</SelectItem>
                </SelectContent>
              </Select>

              <Select value={sortBy} onValueChange={setSortBy}>
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="name">Name</SelectItem>
                  <SelectItem value="category">Category</SelectItem>
                  <SelectItem value="health">Health</SelectItem>
                  <SelectItem value="usage">Usage</SelectItem>
                  <SelectItem value="success">Success Rate</SelectItem>
                  <SelectItem value="lastUsed">Last Used</SelectItem>
                </SelectContent>
              </Select>

              <div className="flex border rounded-md">
                <Button
                  variant={viewMode === "grid" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setViewMode("grid")}
                  className="rounded-r-none"
                >
                  <Grid3X3 className="h-4 w-4" />
                </Button>
                <Button
                  variant={viewMode === "list" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setViewMode("list")}
                  className="rounded-l-none border-l"
                >
                  <List className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Category Tags */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant={selectedCategory === null ? "default" : "outline"}
          size="sm"
          onClick={() => setSelectedCategory(null)}
        >
          All ({tools.length})
        </Button>
        {getCategories().map(category => {
          const count = tools.filter(tool => tool.category === category).length
          return (
            <Button
              key={category}
              variant={selectedCategory === category ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedCategory(category)}
            >
              {category} ({count})
            </Button>
          )
        })}
      </div>

      {/* Results Summary */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          Showing {filteredTools.length} of {tools.length} tools
          {searchQuery && ` for "${searchQuery}"`}
        </span>
        {filteredTools.length > 0 && (
          <span>
            Sorted by {sortBy}
          </span>
        )}
      </div>

      {/* Tools Display */}
      {viewMode === "grid" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredTools.map((tool) => (
            <Card
              key={tool.id}
              className="hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => { setSelectedToolName(tool.name); setManagerOpen(true); }}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`w-3 h-3 rounded-full ${getStatusColor(tool.status)}`} />
                    <div>
                      <CardTitle className="text-base">{tool.name}</CardTitle>
                      <Badge variant="outline" className="text-xs mt-1">
                        v{tool.version}
                      </Badge>
                    </div>
                  </div>
                  <Badge variant="secondary" className="text-xs">
                    {tool.category}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
                  {tool.description}
                </p>

                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span>Health</span>
                    <span className={`font-medium ${getHealthColor(tool.healthScore)}`}>
                      {tool.healthScore}%
                    </span>
                  </div>
                  <Progress value={tool.healthScore} className="h-1" />

                  <div className="flex items-center justify-between text-xs">
                    <span>Success Rate</span>
                    <span>{tool.successRate.toFixed(1)}%</span>
                  </div>
                  <Progress value={tool.successRate} className="h-1" />
                </div>

                <div className="flex flex-wrap gap-1 mt-3">
                  {tool.capabilities.slice(0, 3).map((capability, index) => (
                    <Badge key={index} variant="outline" className="text-xs">
                      {capability}
                    </Badge>
                  ))}
                  {tool.capabilities.length > 3 && (
                    <Badge variant="outline" className="text-xs">
                      +{tool.capabilities.length - 3}
                    </Badge>
                  )}
                </div>
                {tool.requiredCredentials?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {tool.requiredCredentials.map((cred, idx) => (
                      <Badge key={idx} variant="outline" className="text-[10px]">
                        <Key className="mr-1 h-3 w-3" />{cred}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
              <CardFooter className="pt-0">
                <div className="flex items-center justify-between w-full text-xs text-muted-foreground">
                  <span>{tool.totalExecutions} executions</span>
                  <div className="flex items-center gap-2">
                    <span>{formatLastUsed(tool.lastUsed)}</span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); setSelectedToolName(tool.name); setCredOpen(true); }}
                    >
                      <Key className="h-3 w-3 mr-1" /> Creds
                    </Button>
                  </div>
                </div>
              </CardFooter>
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredTools.map((tool) => (
            <Card key={tool.id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4 flex-1">
                    <div className="flex items-center gap-2">
                      <div className={`w-3 h-3 rounded-full ${getStatusColor(tool.status)}`} />
                      <div>
                        <h3 className="font-medium">{tool.name}</h3>
                        <p className="text-sm text-muted-foreground">{tool.description}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 text-sm">
                      <Badge variant="outline">{tool.category}</Badge>
                      <Badge variant="outline">v{tool.version}</Badge>
                      <span className={`font-medium ${getHealthColor(tool.healthScore)}`}>
                        {tool.healthScore}% healthy
                      </span>
                      <span>{tool.successRate.toFixed(1)}% success</span>
                      {tool.requiredCredentials?.length > 0 && (
                        <div className="hidden md:flex flex-wrap gap-1">
                          {tool.requiredCredentials.map((cred, idx) => (
                            <Badge key={idx} variant="outline" className="text-[10px]">
                              <Key className="mr-1 h-3 w-3" />{cred}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">
                      {tool.totalExecutions} calls
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {formatLastUsed(tool.lastUsed)}
                    </span>
                    <Button size="sm" variant="outline" onClick={() => { setSelectedToolName(tool.name); setManagerOpen(true); }}>
                      <Settings className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => { setSelectedToolName(tool.name); setCredOpen(true); }}>
                      <Key className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {filteredTools.length === 0 && (
        <Card>
          <CardContent className="flex items-center justify-center p-8">
            <div className="text-center">
              <Wrench className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium mb-2">No Tools Found</h3>
              <p className="text-muted-foreground">
                {searchQuery || categoryFilter !== "all" || statusFilter !== "all"
                  ? "Try adjusting your search or filter criteria."
                  : "No MCP tools are currently available."
                }
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Manager Modal */}
      <Dialog open={managerOpen} onOpenChange={setManagerOpen}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>MCP Tool Manager</DialogTitle>
          </DialogHeader>
          {selectedToolName && (
            <MCPToolManager preselectToolName={selectedToolName} />
          )}
        </DialogContent>
      </Dialog>

      {/* Credential Manager Modal */}
      <Dialog open={credOpen} onOpenChange={setCredOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Configure Credentials</DialogTitle>
          </DialogHeader>
          {selectedToolName && (
            <CredentialManager toolName={selectedToolName} onClose={() => setCredOpen(false)} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
