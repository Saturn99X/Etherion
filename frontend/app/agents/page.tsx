import { AgentRegistry } from "@/components/agent-registry"
import { AgentTeams } from "@/components/agent-teams"
import { AppShell } from "@/components/app-shell"
import { AuthGuard } from "@/components/auth/auth-guard"

export default function AgentsPage() {
  return (
    <AuthGuard>
      <AppShell>
        <div className="space-y-12">
          <AgentTeams />
          <AgentRegistry />
        </div>
      </AppShell>
    </AuthGuard>
  )
}
