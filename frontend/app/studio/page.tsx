import { VibeCodeStudioPage } from "@/components/vibe-code-studio"
import { AppShell } from "@/components/app-shell"
import { AuthGuard } from "@/components/auth/auth-guard"

export default function StudioPage() {
  return (
    <AuthGuard>
      <AppShell>
        <VibeCodeStudioPage />
      </AppShell>
    </AuthGuard>
  )
}
