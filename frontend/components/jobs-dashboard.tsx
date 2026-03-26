"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Search, Filter, ChevronLeft, ChevronRight } from "lucide-react"
import { useApolloClient } from "@/components/apollo-provider";
import { GET_JOB_HISTORY_QUERY, GET_JOB_DETAILS_QUERY } from "@/lib/graphql-operations"

interface JobHistoryItem {
  id: string
  goal: string
  status: string
  createdAt: string
  completedAt?: string
  duration: string
  totalCost: string
  modelUsed?: string
  tokenCount?: number
  successRate?: number
  threadId?: string
}

interface JobHistoryPageInfo {
  hasNextPage: boolean
  hasPreviousPage: boolean
}

interface JobHistory {
  jobs: JobHistoryItem[]
  totalCount: number
  pageInfo: JobHistoryPageInfo
}

const getStatusVariant = (status: string) => {
  switch (status.toLowerCase()) {
    case "completed":
      return "default"
    case "running":
      return "secondary"
    case "failed":
      return "destructive"
    case "pending":
      return "outline"
    case "queued":
      return "outline"
    case "cancelled":
      return "outline"
    default:
      return "outline"
  }
}

const formatDuration = (durationSeconds: number): string => {
  if (durationSeconds < 60) {
    return `${durationSeconds}s`
  } else if (durationSeconds < 3600) {
    const minutes = Math.floor(durationSeconds / 60)
    const seconds = durationSeconds % 60
    return `${minutes}m ${seconds}s`
  } else {
    const hours = Math.floor(durationSeconds / 3600)
    const minutes = Math.floor((durationSeconds % 3600) / 60)
    return `${hours}h ${minutes}m`
  }
}

const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleString()
}

export function JobsDashboard() {
  const router = useRouter()
  const [jobs, setJobs] = useState<JobHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [currentPage, setCurrentPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [pageInfo, setPageInfo] = useState<JobHistoryPageInfo>({ hasNextPage: false, hasPreviousPage: false })
  const client = useApolloClient();
  const itemsPerPage = 10

  useEffect(() => {
    fetchJobHistory()
  }, [currentPage, statusFilter])

  const fetchJobHistory = async () => {
    try {
      setLoading(true)
      setError(null)

      const { data } = await client.query({
        query: GET_JOB_HISTORY_QUERY,
        variables: {
          limit: itemsPerPage,
          offset: (currentPage - 1) * itemsPerPage,
          status: statusFilter === "all" ? null : statusFilter,
          date_from: null,
          date_to: null
        }
      })

      const jobHistory: JobHistory = (data as any).getJobHistory
      setJobs(jobHistory.jobs)
      setTotalCount(jobHistory.totalCount)
      setPageInfo(jobHistory.pageInfo)
    } catch (error) {
      console.error('Failed to fetch job history:', error)
      setError('Failed to load job history')
    } finally {
      setLoading(false)
    }
  }

  const handleViewDetails = async (jobId: string) => {
    try {
      const { data } = await client.query({
        query: GET_JOB_DETAILS_QUERY,
        variables: { job_id: jobId }
      })

      // TODO: Show job details in a modal or navigate to details page
      console.log('Job details:', (data as any).getJobDetails)
    } catch (error) {
      console.error('Failed to fetch job details:', error)
    }
  }

  // Optional deep-link to chat when backend provides threadId mapping
  const handleOpenChat = (job: JobHistoryItem) => {
    if (job.threadId) {
      router.push(`/interact?thread=${encodeURIComponent(job.threadId)}`)
    }
  }

  const filteredJobs = jobs.filter((job) => {
    const matchesSearch = job.goal.toLowerCase().includes(searchTerm.toLowerCase())
    return matchesSearch
  })

  const totalPages = Math.ceil(totalCount / itemsPerPage)

  if (loading) {
    return (
      <div className="space-y-6 glass-container">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Jobs Dashboard</h1>
            <p className="text-muted-foreground">Monitor and manage your AI job executions</p>
          </div>
        </div>
        <div className="flex items-center justify-center py-12">
          <div className="text-muted-foreground">Loading job history...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6 glass-container">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Jobs Dashboard</h1>
            <p className="text-muted-foreground">Monitor and manage your AI job executions</p>
          </div>
        </div>
        <Card className="text-center py-12">
          <CardContent>
            <div className="text-destructive mb-4">{error}</div>
            <Button onClick={fetchJobHistory} variant="outline">
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6 glass-container">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Jobs Dashboard</h1>
          <p className="text-muted-foreground">Monitor and manage your AI job executions</p>
        </div>
      </div>

      <Card className="glass-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search by goal..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="running">Running</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="queued">Queued</SelectItem>
                <SelectItem value="cancelled">Cancelled</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card className="glass-card">
        <CardHeader>
          <CardTitle>Job History ({totalCount} total)</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Job ID</TableHead>
                <TableHead>Goal</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created At</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Total Cost</TableHead>
                <TableHead>Model Used</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredJobs.map((job) => (
                <TableRow key={job.id}>
                  <TableCell className="font-mono text-sm">{job.id}</TableCell>
                  <TableCell className="max-w-md">
                    <div className="truncate" title={job.goal}>
                      {job.goal}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={getStatusVariant(job.status)}>{job.status}</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{formatDate(job.createdAt)}</TableCell>
                  <TableCell className="text-sm">{job.duration}</TableCell>
                  <TableCell className="font-medium">{job.totalCost}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {job.modelUsed || '-'}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleViewDetails(job.id)}
                    >
                      Details
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="ml-1"
                      onClick={() => handleOpenChat(job)}
                      disabled={!job.threadId}
                      title={job.threadId ? "Open Chat" : "Thread not available yet"}
                    >
                      Open Chat
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-6">
              <div className="text-sm text-muted-foreground">
                Page {currentPage} of {totalPages}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                  disabled={!pageInfo.hasPreviousPage}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                  disabled={!pageInfo.hasNextPage}
                >
                  Next
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
