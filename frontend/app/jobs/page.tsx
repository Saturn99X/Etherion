import { JobsDashboard } from "@/components/jobs-dashboard"
import { AppShell } from "@/components/app-shell"
import { AuthGuard } from "@/components/auth/auth-guard"

export default function JobsPage() {
  return (
    <AuthGuard>
      <AppShell>
        <JobsDashboard />
      </AppShell>
    </AuthGuard>
  )
}
