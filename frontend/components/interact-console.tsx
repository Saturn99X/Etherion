"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useApolloClient } from "@/components/apollo-provider";
import { EXECUTE_GOAL_MUTATION } from "@/lib/graphql-operations";
import { useJobStore } from "@/lib/stores/job-store";
import { Badge } from "@/components/ui/badge";

interface InteractConsoleProps {
  teamId: string;
}

export function InteractConsole({ teamId }: InteractConsoleProps) {
  const client = useApolloClient();
  const [goal, setGoal] = useState("");
  const [context, setContext] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const jobs = useJobStore((s) => s.jobs);
  const addJob = useJobStore((s) => s.addJob);
  const subscribeToJob = useJobStore((s) => s.subscribeToJob);

  const onSubmit = async () => {
    if (!goal.trim()) return;
    try {
      setSubmitting(true);
      const { data } = await client.mutate({
        mutation: EXECUTE_GOAL_MUTATION,
        variables: {
          goalInput: {
            goal: goal.trim(),
            context: context.trim() || null,
            agentTeamId: teamId,
          },
        },
      });
      const resp = data?.executeGoal;
      if (resp?.success && resp?.job_id) {
        addJob(resp.job_id);
        subscribeToJob(resp.job_id);
        setGoal("");
        setContext("");
      }
    } catch (e) {
      console.error("Failed to execute goal", e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card className="glass-card">
        <CardHeader>
          <CardTitle>Interact</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-muted-foreground">Team: <span className="font-mono">{teamId}</span></div>
          <Textarea
            placeholder="Describe your goal..."
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            rows={4}
          />
          <Input
            placeholder="Optional context (links, IDs, hints)"
            value={context}
            onChange={(e) => setContext(e.target.value)}
          />
          <div className="flex justify-end">
            <Button onClick={onSubmit} disabled={submitting || !goal.trim()}>
              {submitting ? "Submitting..." : "Run"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {Object.values(jobs).length === 0 && (
          <div className="text-sm text-muted-foreground">No jobs yet. Submit a goal above.</div>
        )}
        {Object.values(jobs).map((job) => (
          <Card key={job.id} className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Job {job.id}</CardTitle>
                <Badge variant={job.isFailed ? "destructive" : job.isCompleted ? "default" : "secondary"}>
                  {job.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-muted-foreground">
                {job.currentStep || "Starting..."}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
