import { KnowledgeBaseHub } from "@/components/knowledge-base-hub"
import { AppShell } from "@/components/app-shell"
import { AuthGuard } from "@/components/auth/auth-guard"

export default function KnowledgePage() {
  return (
    <AuthGuard>
      <AppShell>
        <KnowledgeBaseHub />
      </AppShell>
    </AuthGuard>
  )
}
