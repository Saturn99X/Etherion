import { AppShell } from "@/components/app-shell"
import { AuthGuard } from "@/components/auth/auth-guard"
import { ProjectsDashboard } from "@/components/projects-dashboard"

export default function ProjectsPage() {
  return (
    <AuthGuard>
      <AppShell>
        <ProjectsDashboard />
      </AppShell>
    </AuthGuard>
  )
}
