import { AppShell } from "@/components/app-shell";
import { AuthGuard } from "@/components/auth/auth-guard";
import { InteractConsole } from "@/components/interact-console";
import Link from "next/link";

export default async function InteractPage({ searchParams }: { searchParams?: Promise<{ teamId?: string }> }) {
  const sp = (await searchParams) ?? {};
  const teamId = (sp?.teamId as string) || "";

  return (
    <AuthGuard>
      <AppShell>
        {teamId ? (
          <InteractConsole teamId={teamId} />
        ) : (
          <div className="p-6 text-sm text-muted-foreground">
            Interaction is team-scoped. Select a team from the <Link className="underline" href="/agents">Agents</Link> page or open a deep link like <code className="mx-1">/interact?teamId=team_123</code>.
          </div>
        )}
      </AppShell>
    </AuthGuard>
  );
}
