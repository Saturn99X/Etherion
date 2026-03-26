"use client"

import type React from "react"
import Link from "next/link"
import { useState, useEffect } from "react"
import {
  LayoutDashboard,
  BotMessageSquare,
  History,
  Users,
  BrainCircuit,
  FolderKanban,
  Plug,
  Sparkles,
  Settings,
  Search,
  Plus,
  Menu,
  ChevronLeft,
  ChevronRight,
  Home,
  LogOut,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { useIsMobile } from "@/hooks/use-mobile"
import { ThemeSwitcher } from "@/components/theme-switcher"
import { useAuthStore } from "@/lib/stores/auth-store"
import { LogoutButton } from "@/components/auth/logout-button"
import { ProjectSelector } from "@/components/project-selector"
import { Project } from "@/lib/services/project-service"
import { TenantUIEventsSubscriber } from "@/components/tenant-ui-events-subscriber"
import { useToast } from "@/hooks/use-toast"
import { decodeJwt } from "@/lib/jwt"
import { useRouter } from "next/navigation"

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const router = useRouter()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [tenantId, setTenantId] = useState<number | null>(null)
  const isMobile = useIsMobile()
  const { user, isAuthenticated, token } = useAuthStore()
  const { toast } = useToast()

  // Derive tenantId from JWT token claims
  useEffect(() => {
    try {
      const t = token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null)
      if (!t) {
        setTenantId(null)
        return
      }
      const payload = decodeJwt(t)
      const raw = (payload && ((payload as any).tenant_id ?? (payload as any).tenantId)) as number | string | undefined
      const n = Number(raw)
      setTenantId(Number.isFinite(n) && n > 0 ? n : null)
    } catch {
      setTenantId(null)
    }
  }, [token])

  const SidebarContent = () => (
    <div className="flex h-full flex-col glass-strong border-r border-border">
      {/* Header */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg chromatic-border glow-purple overflow-hidden">
          <img src="/logo.png" alt="Etherion" className="h-6 w-6 object-contain relative z-10" />
        </div>
        {(!sidebarCollapsed || isMobile) && <span className="text-lg font-semibold text-foreground">Etherion</span>}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-4">
        {navigationItems.map((item) => {
          const Icon = item.icon
          return (
            <TooltipProvider key={item.href}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link href={item.href}>
                    <Button
                      variant="ghost"
                      className={cn(
                        "w-full justify-start gap-3 text-muted-foreground hover:glass hover:text-foreground hover:glow transition-all duration-300",
                        sidebarCollapsed && !isMobile && "justify-center px-2",
                      )}
                    >
                      <Icon className="h-5 w-5 shrink-0" />
                      {(!sidebarCollapsed || isMobile) && <span className="truncate">{item.label}</span>}
                    </Button>
                  </Link>
                </TooltipTrigger>
                {sidebarCollapsed && !isMobile && (
                  <TooltipContent side="right" className="glass-strong border-border">
                    <p>{item.label}</p>
                  </TooltipContent>
                )}
              </Tooltip>
            </TooltipProvider>
          )
        })}
      </nav>

      {/* Search */}
      <div className="px-4 pb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search"
            className={cn(
              "pl-9 glass border-border text-foreground placeholder:text-muted-foreground focus:glow-cyan",
              sidebarCollapsed && !isMobile && "px-9",
            )}
          />
        </div>
      </div>

      {/* New Task / New Agent Buttons */}
      <div className="px-4 pb-4">
        <Button
          className="w-full gap-2 iridescent text-foreground font-semibold hover:scale-105 transition-all duration-300 glow-purple"
          size={sidebarCollapsed && !isMobile ? "icon" : "default"}
          onClick={() => router.push('/interact')}
        >
          <Plus className="h-4 w-4" />
          {(!sidebarCollapsed || isMobile) && "New Task"}
        </Button>
        {(!sidebarCollapsed || isMobile) && (
          <Button
            variant="ghost"
            className="mt-2 w-full gap-2 glass text-foreground font-medium hover:glow-purple"
            size="sm"
            onClick={() => router.push('/studio')}
          >
            <Plus className="h-4 w-4" /> New Agent
          </Button>
        )}
      </div>

      {/* Footer Selects */}
      <div className="border-t border-border p-4 space-y-3">
        {(!sidebarCollapsed || isMobile) && (
          <>
            <ProjectSelector
              selectedProjectId={selectedProject?.id}
              onProjectSelect={setSelectedProject}
            />
            {/* Tenant switcher removed per scope */}
          </>
        )}
      </div>
    </div>
  )

  return (
    <TooltipProvider>
      <div className="flex h-screen bg-background relative overflow-hidden">
        {/* Desktop Sidebar */}
        {!isMobile && (
          <div className={cn("relative transition-all duration-300 z-10", sidebarCollapsed ? "w-16" : "w-64")}>
            <SidebarContent />
            <Button
              variant="ghost"
              size="icon"
              className="absolute -right-3 top-6 z-10 h-6 w-6 rounded-full glass border-border shadow-lg hover:glow-cyan transition-all duration-300"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            >
              {sidebarCollapsed ? (
                <ChevronRight className="h-3 w-3 text-foreground" />
              ) : (
                <ChevronLeft className="h-3 w-3 text-foreground" />
              )}
            </Button>
          </div>
        )}

        {/* Main Content */}
        <div className="flex flex-1 flex-col overflow-hidden relative z-10">
          {/* Tenant UI events subscriber for toast notifications (only when tenantId is known) */}
          {tenantId && (
            <TenantUIEventsSubscriber tenantId={tenantId} onEvent={(evt) => {
              if (evt?.message) {
                toast({ title: "Update", description: evt.message })
              }
            }} />
          )}
          {/* Top Bar */}
          <header className="flex h-16 items-center justify-between glass border-b border-border px-6">
            <div className="flex items-center gap-4">
              {/* Mobile Menu */}
              {isMobile && (
                <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
                  <SheetTrigger asChild>
                    <Button variant="ghost" size="icon" className="text-foreground hover:glow">
                      <Menu className="h-5 w-5" />
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="left" className="w-64 p-0 glass-strong border-border">
                    <SidebarContent />
                  </SheetContent>
                </Sheet>
              )}

              {/* Breadcrumb */}
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/" className="text-muted-foreground hover:text-foreground">
                      <Home className="h-4 w-4" />
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator className="text-muted-foreground" />
                  <BreadcrumbItem>
                    <BreadcrumbPage className="text-foreground font-medium">Dashboard</BreadcrumbPage>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </div>

              {/* User Menu */}
            {isAuthenticated && user && (
              <div className="flex items-center gap-2">
                <ThemeSwitcher />

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      className="flex items-center gap-2 px-2 text-foreground hover:glow transition-all duration-300"
                    >
                      <Avatar className="h-8 w-8 ring-2 ring-border">
                        <AvatarImage src={user.profile_picture_url} />
                        <AvatarFallback className="bg-gradient-to-br from-purple-500 to-cyan-500 text-white">
                          {user.name.split(' ').map(n => n[0]).join('').toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <span className="hidden sm:inline-block font-medium">{user.name}</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56 glass-strong border-border">
                    <DropdownMenuItem className="text-foreground hover:glass">
                      <Settings className="mr-2 h-4 w-4" />
                      Settings
                    </DropdownMenuItem>
                    <DropdownMenuItem className="text-foreground hover:glass">
                      <LogoutButton variant="ghost" size="sm" showText={false} />
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            )}
          </header>

          {/* Main Content Area */}
          <main className="flex-1 overflow-auto p-6 relative">
            <div className="glass-subtle rounded-xl p-6 min-h-full">{children}</div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  )
}

const navigationItems = [
  { icon: Sparkles, label: "Agents Forgery", href: "/studio" },
  { icon: BotMessageSquare, label: "Interact", href: "/interact" },
  { icon: Users, label: "Agents Teams", href: "/agents" },
  { icon: BrainCircuit, label: "Knowledge Base", href: "/knowledge" },
  { icon: Plug, label: "Integrations", href: "/integrations" },
  { icon: FolderKanban, label: "Projects", href: "/projects" },
  { icon: History, label: "Jobs", href: "/jobs" },
  { icon: FolderKanban, label: "Repository", href: "/repository" },
  { icon: Settings, label: "Settings", href: "/settings" },
]
