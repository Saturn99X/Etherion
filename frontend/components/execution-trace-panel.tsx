"use client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { CheckCircle, Loader2, Brain } from "lucide-react"

interface ToolCallCardProps {
  toolName: string
  arguments: string
  output: string
}

function ToolCallCard({ toolName, arguments: args, output }: ToolCallCardProps) {
  return (
    <Card className="glass border-white/10">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-white">{toolName}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-2 text-sm">
          <div>
            <span className="font-medium text-white/80">Arguments:</span>
            <p className="text-xs glass-subtle p-2 rounded mt-1 text-white/90 font-mono">{args}</p>
          </div>
          <div>
            <span className="font-medium text-white/80">Output:</span>
            <p className="text-xs glass-subtle p-2 rounded mt-1 text-white/90 font-mono">{output}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function ArtifactList() {
  return (
    <div className="space-y-4">
      <h4 className="text-sm font-medium text-white">Generated Artifacts</h4>

      <div className="glass-card p-3 rounded border-white/10 glow-hover transition-all duration-300">
        <h5 className="text-xs font-medium mb-2 text-white/90">Markdown Document</h5>
        <div className="text-xs text-white/70 font-mono">
          # Sample Markdown This is a preview of generated markdown content...
        </div>
      </div>

      <div className="glass-card p-3 rounded border-white/10 glow-hover transition-all duration-300">
        <h5 className="text-xs font-medium mb-2 text-white/90">Generated Image</h5>
        <img
          src="/ai-generated-visualization.jpg"
          alt="Generated visualization"
          className="rounded border border-white/20 glow-subtle"
        />
      </div>

      <div className="glass-card p-3 rounded border-white/10 glow-hover transition-all duration-300">
        <h5 className="text-xs font-medium mb-2 text-white/90">Data Table</h5>
        <table className="text-xs w-full text-white/80">
          <thead>
            <tr className="border-b border-white/20">
              <th className="text-left p-1">Column 1</th>
              <th className="text-left p-1">Column 2</th>
              <th className="text-left p-1">Column 3</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="p-1">Data 1</td>
              <td className="p-1">Data 2</td>
              <td className="p-1">Data 3</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

interface ExecutionStep {
  id: string
  title: string
  summary: string
  status: "completed" | "in-progress" | "pending"
  details?: string
  toolCall?: ToolCallCardProps
  hasArtifacts?: boolean
}

export function ExecutionTracePanel() {
  const steps: ExecutionStep[] = [
    {
      id: "thinking",
      title: "Thinking",
      summary: "Analyzing the user request and planning approach",
      status: "completed",
      details:
        "Breaking down the complex query into manageable components and identifying the best strategy for providing a comprehensive response.",
    },
    {
      id: "clarifying",
      title: "Clarifying the question",
      summary: "Understanding context and requirements",
      status: "completed",
      details: "Reviewing the user's specific needs and ensuring all aspects of the request are properly understood.",
    },
    {
      id: "executing",
      title: "Executing Tool",
      summary: "Running SearchWeb to gather information",
      status: "in-progress",
      details: "Performing web search to find the most current and relevant information.",
      toolCall: {
        toolName: "SearchWeb",
        arguments: '{"query": "latest AI developments 2024", "isFirstParty": false}',
        output: "Found 15 relevant articles about recent AI breakthroughs...",
      },
    },
    {
      id: "generating",
      title: "Generating Response",
      summary: "Creating comprehensive answer with artifacts",
      status: "pending",
      hasArtifacts: true,
    },
  ]

  const getStepIcon = (status: ExecutionStep["status"]) => {
    switch (status) {
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-400 glow-hover" />
      case "in-progress":
        return <Loader2 className="h-4 w-4 text-cyan-400 animate-spin glow-cyan" />
      case "pending":
        return <div className="h-4 w-4 rounded-full border-2 border-white/30" />
    }
  }

  return (
    <Card className="glass-card border-white/20 glow-hover transition-all duration-300">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-white">
          <Brain className="h-5 w-5 text-white" />
          <span className="text-white">Execution Trace</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-4">
          <div className="flex flex-col items-center">
            {steps.map((step, index) => (
              <div key={step.id} className="flex flex-col items-center">
                {getStepIcon(step.status)}
                {index < steps.length - 1 && (
                  <div className="w-px h-8 bg-gradient-to-b from-white/30 to-white/10 my-2" />
                )}
              </div>
            ))}
          </div>

          <div className="flex-1">
            <Accordion type="multiple" className="space-y-2">
              {steps.map((step) => (
                <AccordionItem
                  key={step.id}
                  value={step.id}
                  className="glass border-white/20 rounded-lg px-3 hover:glow-hover transition-all duration-300"
                >
                  <AccordionTrigger className="text-sm hover:no-underline text-white">
                    <div className="flex flex-col items-start text-left">
                      <span className="font-medium">{step.title}</span>
                      <span className="text-xs text-white/70">{step.summary}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="space-y-3">
                    {step.details && <p className="text-sm text-white/80">{step.details}</p>}

                    {step.toolCall && <ToolCallCard {...step.toolCall} />}

                    {step.hasArtifacts && <ArtifactList />}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
