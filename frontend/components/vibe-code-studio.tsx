"use client"

import { useMemo, useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Bot, User } from "lucide-react"
import { GoalInputBar } from "./goal-input-bar"
import AgentBlueprintUI from "@/components/ui/triggered-ui/agent-blueprint-ui"
import { useJobStore } from "@/lib/stores/job-store"

interface Message {
  id: string
  type: "user" | "assistant"
  content: string
  timestamp: Date
}

export function VibeCodeStudioPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      type: "assistant",
      content:
        "Welcome to Agents Forgery! I'll help you create custom AI agents. Describe what kind of agent you'd like to build, including its purpose, capabilities, and any specific tools it should have access to.",
      timestamp: new Date(),
    },
  ])

  const handleSendMessage = (content: string, attachments: any[]) => {
    const userMessage: Message = {
      id: Date.now().toString(),
      type: "user",
      content,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMessage])
  }

  // Read latest jobId from job store to drive live blueprint UI
  const jobs = useJobStore((s) => s.jobs)
  const lastJobId = useMemo(() => {
    const arr = Object.values(jobs || {}) as any[]
    if (!arr.length) return ""
    arr.sort((a, b) => (a.createdAt?.getTime?.() || 0) - (b.createdAt?.getTime?.() || 0))
    return arr[arr.length - 1]?.id || ""
  }, [jobs])

  return (
    <div className="flex flex-col h-full">
      <div className="border-b p-4">
        <h1 className="text-2xl font-bold">Agents Forgery</h1>
        <p className="text-muted-foreground">Forge and customize AI agents for your specific needs</p>
      </div>

      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4 max-w-4xl mx-auto">
          {lastJobId ? (<AgentBlueprintUI jobId={lastJobId} />) : null}
          {messages.map((message) => (
            <div key={message.id} className={`flex gap-3 ${message.type === "user" ? "justify-end" : "justify-start"}`}>
              {message.type === "assistant" && (
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <Bot className="h-4 w-4 text-primary" />
                </div>
              )}
              <div className={`max-w-2xl space-y-3 ${message.type === "user" ? "order-first" : ""}`}>
                <div
                  className={`p-3 rounded-lg ${
                    message.type === "user" ? "bg-primary text-primary-foreground ml-auto" : "bg-muted"
                  }`}
                >
                  {message.content}
                </div>
              </div>
              {message.type === "user" && (
                <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0">
                  <User className="h-4 w-4" />
                </div>
              )}
            </div>
          ))}
        </div>
      </ScrollArea>

      <div className="border-t p-4">
        <div className="max-w-4xl mx-auto">
          <GoalInputBar onSubmit={handleSendMessage} placeholder="Describe the agent you want to create..." autoFocus />
        </div>
      </div>
    </div>
  )
}
