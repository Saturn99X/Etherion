import { AppShell } from "@/components/app-shell"
import { ThreadView } from "@/components/thread-view"
import { AuthGuard } from "@/components/auth/auth-guard"

export default function HomePage() {
  return (
    <AuthGuard>
      <AppShell>
        <ThreadView />
      </AppShell>
    </AuthGuard>
  )
}
