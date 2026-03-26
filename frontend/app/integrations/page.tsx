import { IntegrationHub } from "@/components/integration-hub"
import { AppShell } from "@/components/app-shell"
import { AuthGuard } from "@/components/auth/auth-guard"

export default function IntegrationsPage() {
  return (
    <AuthGuard>
      <AppShell>
        <IntegrationHub />
      </AppShell>
    </AuthGuard>
  )
}
