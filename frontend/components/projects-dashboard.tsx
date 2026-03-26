"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApolloClient } from "@/components/apollo-provider"
import { GET_PROJECTS_QUERY, CREATE_PROJECT_MUTATION, UPDATE_PROJECT_MUTATION, DELETE_PROJECT_MUTATION } from "@/lib/graphql-operations"
import { RefreshCw, Plus, Save, Trash2, Edit, X } from "lucide-react"

interface ProjectItem {
  id: string
  name: string
  description?: string
  createdAt?: string
  userId?: string
}

export function ProjectsDashboard() {
  const client = useApolloClient()
  const [projects, setProjects] = useState<ProjectItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasAttemptedLoad, setHasAttemptedLoad] = useState(false)

  // New project state
  const [newName, setNewName] = useState("")
  const [newDesc, setNewDesc] = useState("")

  // Edit state
  const [editId, setEditId] = useState<string | null>(null)
  const [editName, setEditName] = useState("")
  const [editDesc, setEditDesc] = useState("")

  const loadProjects = async () => {
    try {
      setLoading(true)
      setError(null)
      const { data } = await client.query({ query: GET_PROJECTS_QUERY, fetchPolicy: "network-only" })
      const list = (data as any)?.getProjectsByTenant || []
      setProjects(list)
      setHasAttemptedLoad(true)
    } catch (e) {
      console.error("Failed to load projects", e)
      setError("Failed to load projects. Backend may not be running.")
      setHasAttemptedLoad(true)
    } finally {
      setLoading(false)
    }
  }

  // CRITICAL FIX: Only load once on mount, prevent infinite retry loop
  useEffect(() => {
    if (!hasAttemptedLoad) {
      loadProjects()
    }
  }, [hasAttemptedLoad])

  const createProject = async () => {
    if (!newName.trim()) return
    try {
      setLoading(true)
      await client.mutate({
        mutation: CREATE_PROJECT_MUTATION,
        variables: { project_input: { name: newName, description: newDesc || undefined } },
      })
      setNewName("")
      setNewDesc("")
      await loadProjects()
    } catch (e) {
      console.error("Create project failed", e)
      setError("Create project failed")
    } finally {
      setLoading(false)
    }
  }

  const startEdit = (p: ProjectItem) => {
    setEditId(p.id)
    setEditName(p.name)
    setEditDesc(p.description || "")
  }

  const cancelEdit = () => {
    setEditId(null)
    setEditName("")
    setEditDesc("")
  }

  const saveEdit = async () => {
    if (!editId || !editName.trim()) return
    try {
      setLoading(true)
      await client.mutate({
        mutation: UPDATE_PROJECT_MUTATION,
        variables: { project_id: Number(editId), project_input: { name: editName, description: editDesc || undefined } },
      })
      cancelEdit()
      await loadProjects()
    } catch (e) {
      console.error("Update project failed", e)
      setError("Update project failed")
    } finally {
      setLoading(false)
    }
  }

  const deleteProject = async (id: string) => {
    try {
      setLoading(true)
      await client.mutate({ mutation: DELETE_PROJECT_MUTATION, variables: { project_id: Number(id) } })
      await loadProjects()
    } catch (e) {
      console.error("Delete project failed", e)
      setError("Delete project failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
          <p className="text-muted-foreground">Organize conversations and jobs by project</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadProjects} disabled={loading}>
          <RefreshCw className="mr-2 h-4 w-4" /> Refresh
        </Button>
      </div>

      <Card className="glass-card">
        <CardHeader>
          <CardTitle>Create Project</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid md:grid-cols-2 gap-2">
            <Input placeholder="Project name" value={newName} onChange={(e) => setNewName(e.target.value)} />
            <Textarea placeholder="Description (optional)" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} rows={1} />
          </div>
          <Button onClick={createProject} disabled={loading || !newName.trim()}>
            <Plus className="mr-2 h-4 w-4" /> Create
          </Button>
        </CardContent>
      </Card>

      <Card className="glass-card">
        <CardHeader>
          <CardTitle>Project List</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projects.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">
                    {editId === p.id ? (
                      <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
                    ) : (
                      p.name
                    )}
                  </TableCell>
                  <TableCell>
                    {editId === p.id ? (
                      <Textarea rows={1} value={editDesc} onChange={(e) => setEditDesc(e.target.value)} />
                    ) : (
                      p.description || "-"
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{p.createdAt ? new Date(p.createdAt).toLocaleString() : "-"}</TableCell>
                  <TableCell className="text-right space-x-2">
                    {editId === p.id ? (
                      <>
                        <Button size="sm" onClick={saveEdit} disabled={loading}>
                          <Save className="h-4 w-4 mr-1" /> Save
                        </Button>
                        <Button size="sm" variant="outline" onClick={cancelEdit}>
                          <X className="h-4 w-4 mr-1" /> Cancel
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button size="sm" variant="outline" onClick={() => startEdit(p)}>
                          <Edit className="h-4 w-4 mr-1" /> Edit
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => deleteProject(p.id)}>
                          <Trash2 className="h-4 w-4 mr-1" /> Delete
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {projects.length === 0 && <div className="text-sm text-muted-foreground mt-4">No projects yet.</div>}
          {error && <div className="text-sm text-destructive mt-2">{error}</div>}
        </CardContent>
      </Card>
    </div>
  )
}
