"use client"

import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Sparkles, Check } from "lucide-react"

interface AgentBlueprintPreviewProps {
  agentName: string
  systemPrompt: string
  tools: string[]
}

export function AgentBlueprintPreview({ agentName, systemPrompt, tools }: AgentBlueprintPreviewProps) {
  return (
    <Card className="glass-card border-blue-500/50 shadow-blue-500/20 shadow-lg">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-blue-600 dark:text-blue-400">
          <Sparkles className="w-5 h-5" />
          Agent Blueprint: {agentName}
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="space-y-2">
          <h4 className="font-semibold text-foreground">System Prompt</h4>
          <div className="bg-muted/50 p-4 rounded-lg border">
            <pre className="text-sm text-muted-foreground whitespace-pre-wrap font-mono">{systemPrompt}</pre>
          </div>
        </div>

        <div className="space-y-2">
          <h4 className="font-semibold text-foreground">Tools</h4>
          <div className="flex flex-wrap gap-2">
            {tools.map((tool, index) => (
              <Badge key={index} variant="secondary">
                {tool}
              </Badge>
            ))}
          </div>
        </div>
      </CardContent>

      <CardFooter>
        <Button className="w-full bg-blue-600 hover:bg-blue-700 text-white">
          <Check className="w-4 h-4 mr-2" />
          Validate & Create Agent
        </Button>
      </CardFooter>
    </Card>
  )
}
