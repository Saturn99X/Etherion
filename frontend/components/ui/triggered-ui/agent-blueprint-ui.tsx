"use client";

import { useEffect, useMemo, useState } from "react";
import { useApolloClient } from "@/components/apollo-provider";
import { SUBSCRIBE_TO_EXECUTION_TRACE, CREATE_CUSTOM_AGENT_DEFINITION, CREATE_AGENT_TEAM_FROM_DEFINITION } from "@/lib/graphql-operations";
import AgentBlueprintOrbital from "@/components/ui/triggered-ui/agent-blueprint-orbital";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";

interface AgentBlueprintUIProps {
  jobId: string;
}

interface Blueprint {
  blueprint_id?: string;
  specification?: string;
  tool_requirements?: string[];
  agent_requirements?: any;
  team_structure?: any;
  user_personality?: any;
  platform_prompt?: string;
  recommended_teams?: Array<{
    team_id: string;
    name: string;
    reason?: string;
    deep_link?: string;
    action?: string;
    fit_score?: number;
    readiness?: {
      tools?: Array<{
        name: string;
        credentials_ok?: boolean;
        status?: string;
        manual_approval_required?: boolean;
      }>;
      credentials_ready_count?: number;
      manual_approval_needed?: string[];
      all_ready?: boolean;
    };
  }>;
}

export function AgentBlueprintUI({ jobId }: AgentBlueprintUIProps) {
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const client = useApolloClient();
  const [isValidating, setIsValidating] = useState(false);
  const [validateMsg, setValidateMsg] = useState<string | null>(null);
  useEffect(() => {
    if (!jobId) return;
    const sub = client
      .subscribe({ query: SUBSCRIBE_TO_EXECUTION_TRACE, variables: { job_id: jobId } })
      .subscribe({
        next: (result: any) => {
          const data = result?.data?.subscribeToExecutionTrace;
          if (!data) return;
          const evt = data.additional_data || {};
          if (evt.type === "agent_blueprint_created" && evt.blueprint) {
            setBlueprint(evt.blueprint as Blueprint);
          }
        },
        error: () => {},
      });
    return () => sub.unsubscribe();
  }, [jobId]);

  const previews = useMemo(() => {
    if (!blueprint) return null;
    const sysPrompt = blueprint?.user_personality ? JSON.stringify(blueprint.user_personality, null, 2) : "";
    const tools = Array.isArray(blueprint?.tool_requirements)
      ? blueprint.tool_requirements.join(", ")
      : JSON.stringify(blueprint?.tool_requirements || []);
    const caps = JSON.stringify(blueprint?.team_structure || {}, null, 2);
    return { sysPrompt, tools, caps };
  }, [blueprint]);

  if (!blueprint || !previews) return null;

  return (
    <Card className="glass-card border-white/20">
      <CardHeader className="pb-3">
        <CardTitle className="text-white">Agent Blueprint</CardTitle>
      </CardHeader>
      <CardContent>
        <AgentBlueprintOrbital
          agentName={"Agent Team"}
          blueprintTitle={blueprint.specification || blueprint.blueprint_id || "Blueprint"}
          systemPromptPreview={<pre className="text-xs whitespace-pre-wrap">{previews.sysPrompt}</pre>}
          toolsPreview={<div className="text-xs">{previews.tools}</div>}
          capabilitiesPreview={<pre className="text-xs whitespace-pre-wrap">{previews.caps}</pre>}
          onApprove={() => {}}
          onReject={() => {}}
        />

        {/* Validate & create actions */}
        <div className="mt-4 flex items-center gap-2">
          <Button
            size="sm"
            disabled={isValidating}
            onClick={async () => {
              if (!blueprint) return;
              setIsValidating(true);
              setValidateMsg(null);
              try {
                // Minimal payloads; align with BE schema as it lands
                const defInput: any = {
                  name: blueprint.blueprint_id || blueprint.specification || "Agent Blueprint",
                  specification: blueprint.specification || "",
                  team_structure: blueprint.team_structure || {},
                  user_personality: blueprint.user_personality || {},
                };
                const defRes: any = await client.mutate({
                  mutation: CREATE_CUSTOM_AGENT_DEFINITION,
                  variables: { input: defInput },
                });
                const defId = defRes?.data?.createCustomAgentDefinition?.id;

                const teamInput: any = {
                  name: (blueprint.recommended_teams?.[0]?.name) || "Generated Team",
                  pre_approved_tool_names: blueprint.tool_requirements || [],
                  customAgentIDs: defId ? [defId] : [],
                };
                const teamRes: any = await client.mutate({
                  mutation: CREATE_AGENT_TEAM_FROM_DEFINITION,
                  variables: { team_input: teamInput },
                });
                const teamName = teamRes?.data?.createAgentTeam?.name || "team";
                setValidateMsg(`Validated and created ${teamName}.`);
              } catch (e: any) {
                setValidateMsg(`Validation failed: ${String(e?.message || e)}`);
              } finally {
                setIsValidating(false);
              }
            }}
          >
            {isValidating ? "Validating…" : "Validate"}
          </Button>
          {validateMsg && (
            <span className="text-xs text-white/70">{validateMsg}</span>
          )}
        </div>

        {/* Recommended Teams */}
        {Array.isArray(blueprint.recommended_teams) && blueprint.recommended_teams.length > 0 && (
          <div className="mt-6 space-y-3">
            <h3 className="text-sm font-semibold text-white/90">Recommended Teams</h3>
            <div className="grid gap-3">
              {blueprint.recommended_teams.map((t) => (
                <div key={t.team_id} className="p-3 rounded-md glass border border-white/10">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium text-white">{t.name || t.team_id}</div>
                      <div className="text-xs text-white/70">{t.reason || "Suggested match"}</div>
                      {typeof t.fit_score === "number" && (
                        <div className="text-[10px] text-white/60">Fit score: {t.fit_score}</div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {/* Start with Team */}
                      <Link href={t.deep_link || `/interact?teamId=${encodeURIComponent(t.team_id)}`}>
                        <Button size="sm" className="iridescent">Start with Team</Button>
                      </Link>
                      {/* Connect now */}
                      <Link href="/integrations">
                        <Button variant="secondary" size="sm" className="glass">Connect now</Button>
                      </Link>
                    </div>
                  </div>

                  {/* Readiness details */}
                  {t.readiness?.tools && t.readiness.tools.length > 0 && (
                    <div className="mt-2">
                      <div className="text-xs text-white/80 mb-1">Tool readiness</div>
                      <div className="grid md:grid-cols-2 gap-2">
                        {t.readiness.tools.map((rt) => (
                          <div key={rt.name} className="text-[12px] text-white/80 border border-white/10 rounded px-2 py-1 glass">
                            <span className="font-mono">{rt.name}</span>
                            <span className="mx-2">•</span>
                            <span className={rt.credentials_ok ? "text-green-400" : "text-amber-300"}>
                              {rt.credentials_ok ? "Credentials OK" : "Missing credentials"}
                            </span>
                            <span className="mx-2">•</span>
                            <span className={rt.manual_approval_required ? "text-amber-300" : "text-green-400"}>
                              {rt.manual_approval_required ? "Manual review" : "Stable"}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default AgentBlueprintUI;


