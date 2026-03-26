import { AppShell } from "@/components/app-shell"
import { RepositoryBrowser } from "@/components/repository-browser"
import { AuthGuard } from "@/components/auth/auth-guard"

export default function RepositoryPage() {
  return (
    <AuthGuard>
      <AppShell>
        <RepositoryBrowser />
      </AppShell>
    </AuthGuard>
  )
}


