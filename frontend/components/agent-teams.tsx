"use client";

import { useEffect, useState } from "react";
import { useApolloClient } from "@/components/apollo-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Users, Pencil, Save } from "lucide-react";
import {
  LIST_AGENT_TEAMS_QUERY,
  CREATE_AGENT_TEAM_MUTATION,
  UPDATE_AGENT_TEAM_MUTATION,
} from "@/lib/graphql-operations";

interface AgentTeam {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  lastUpdatedAt: string;
  isActive: boolean;
  isSystemTeam: boolean;
  version: string;
  customAgentIDs: string[];
  preApprovedToolNames: string[];
}

export function AgentTeams() {
  const client = useApolloClient();
  const [teams, setTeams] = useState<AgentTeam[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // Create form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [specification, setSpecification] = useState("");

  // Inline edit state
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");

  useEffect(() => {
    fetchTeams();
  }, []);

  const fetchTeams = async () => {
    try {
      setLoading(true);
      setError(null);
      const { data } = await client.query({
        query: LIST_AGENT_TEAMS_QUERY,
        variables: { limit: 50, offset: 0 },
        fetchPolicy: "network-only",
      });
      setTeams(data?.listAgentTeams || []);
    } catch (e) {
      console.error("Failed to fetch agent teams", e);
      setError("Failed to load agent teams");
    } finally {
      setLoading(false);
    }
  };

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !description.trim() || !specification.trim()) return;
    try {
      setCreating(true);
      const { data } = await client.mutate({
        mutation: CREATE_AGENT_TEAM_MUTATION,
        variables: { team_input: { name: name.trim(), description: description.trim(), specification: specification.trim() } },
      });
      const created = data?.createAgentTeam as AgentTeam;
      if (created) {
        setTeams((prev) => [created, ...prev]);
        setName("");
        setDescription("");
        setSpecification("");
      }
    } catch (e) {
      console.error("Failed to create team", e);
      setError("Failed to create team");
    } finally {
      setCreating(false);
    }
  };

  const startEdit = (t: AgentTeam) => {
    setEditId(t.id);
    setEditName(t.name);
    setEditDescription(t.description);
  };

  const saveEdit = async () => {
    if (!editId) return;
    try {
      await client.mutate({
        mutation: UPDATE_AGENT_TEAM_MUTATION,
        variables: { agent_team_id: editId, name: editName, description: editDescription },
      });
      setTeams((prev) => prev.map((t) => (t.id === editId ? { ...t, name: editName, description: editDescription } : t)));
      setEditId(null);
      setEditName("");
      setEditDescription("");
    } catch (e) {
      console.error("Failed to update team", e);
      setError("Failed to update team");
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Agent Teams</h1>
            <p className="text-muted-foreground">Organize your agents into teams and manage permissions</p>
          </div>
        </div>
        <div className="flex items-center justify-center py-12">
          <div className="text-muted-foreground">Loading agent teams...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Agent Teams</h1>
            <p className="text-muted-foreground">Organize your agents into teams and manage permissions</p>
          </div>
        </div>
        <Card className="text-center py-12">
          <CardContent>
            <div className="text-destructive mb-4">{error}</div>
            <Button onClick={fetchTeams} variant="outline">Retry</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Agent Teams</h1>
          <p className="text-muted-foreground">Organize your agents into teams and manage permissions</p>
        </div>
      </div>

      {/* Create Team */}
      <Card className="glass-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Plus className="h-4 w-4" /> Create Team</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <Input placeholder="Team name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input placeholder="Short description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <Textarea placeholder="Describe what this team should do (specification)" value={specification} onChange={(e) => setSpecification(e.target.value)} rows={3} />
        </CardContent>
        <CardFooter>
          <Button onClick={onCreate} disabled={creating || !name.trim() || !description.trim() || !specification.trim()} className="gap-2">
            <Users className="h-4 w-4" /> {creating ? "Creating..." : "Create Team"}
          </Button>
        </CardFooter>
      </Card>

      {/* Teams list */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {teams.map((t) => (
          <Card key={t.id} className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                {editId === t.id ? (
                  <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
                ) : (
                  <CardTitle className="text-base">{t.name}</CardTitle>
                )}
                {editId === t.id ? (
                  <Button variant="outline" size="sm" onClick={saveEdit} className="gap-1"><Save className="h-4 w-4" />Save</Button>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => startEdit(t)} className="gap-1"><Pencil className="h-4 w-4" />Edit</Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {editId === t.id ? (
                <Textarea value={editDescription} onChange={(e) => setEditDescription(e.target.value)} rows={3} />
              ) : (
                <div className="text-sm text-muted-foreground">{t.description}</div>
              )}
              <div className="text-xs text-muted-foreground">
                Agents: {t.customAgentIDs.length} • Tools: {t.preApprovedToolNames.length}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {teams.length === 0 && (
        <Card className="text-center py-12">
          <CardContent>
            <Users className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium mb-2">No teams yet</h3>
            <p className="text-muted-foreground mb-4">Create your first team to get started</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
