"use client"

import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { FileText, File, ImageIcon, Video, Music, Archive, CheckCircle, Upload, RefreshCw } from "lucide-react"
import { useApolloClient } from "@/components/apollo-provider"
import { LIST_REPOSITORY_ASSETS, GET_INTEGRATIONS_QUERY } from "@/lib/graphql-operations"
import { useAuthStore } from "@/lib/stores/auth-store"
import { decodeJwt } from "@/lib/jwt"
import { BrandAvatar } from "@/components/brand-avatar"

interface RepoAsset {
  assetId: string
  jobId?: string
  filename: string
  mimeType: string
  sizeBytes: number
  createdAt: string
  downloadUrl?: string
}

const getFileIcon = (mime: string) => {
  const type = mime.startsWith("image/") ? "image"
    : mime.startsWith("video/") ? "video"
    : mime.startsWith("audio/") ? "audio"
    : mime === "application/zip" ? "archive"
    : "document"
  switch (type) {
    case "document":
      return FileText
    case "image":
      return ImageIcon
    case "video":
      return Video
    case "audio":
      return Music
    case "archive":
      return Archive
    default:
      return File
  }
}

export function KnowledgeBaseHub() {
  const client = useApolloClient()
  const [assets, setAssets] = useState<RepoAsset[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const { token } = useAuthStore()

  type Integration = { serviceName: string; status: string; lastConnected?: string; errorMessage?: string }
  const PROVIDERS = ["slack", "google", "jira", "hubspot", "notion", "shopify"] as const
  type Provider = typeof PROVIDERS[number]
  const PROVIDER_META: Record<Provider, { name: string; domain: string }> = {
    slack: { name: 'Slack', domain: 'slack.com' },
    google: { name: 'Google', domain: 'google.com' },
    jira: { name: 'Jira', domain: 'atlassian.com' },
    hubspot: { name: 'HubSpot', domain: 'hubspot.com' },
    notion: { name: 'Notion', domain: 'notion.so' },
    shopify: { name: 'Shopify', domain: 'shopify.com' },
  }
  const [integrationMap, setIntegrationMap] = useState<Record<string, Integration | undefined>>({})
  const [intLoading, setIntLoading] = useState<boolean>(false)
  const [intError, setIntError] = useState<string | null>(null)
  const [isPolling, setIsPolling] = useState<boolean>(false)
  const pollIntervalRef = useRef<any>(null)
  const pollTimeoutRef = useRef<any>(null)

  const getTenantId = (): number | null => {
    try {
      const t = token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null)
      if (!t) return null
      const payload = decodeJwt(t)
      const tid = (payload && ((payload as any).tenant_id ?? (payload as any).tenantId)) as number | string | undefined
      if (!tid) return null
      const n = Number(tid)
      return Number.isFinite(n) ? n : null
    } catch {
      return null
    }
  }

  const getApiBase = (): string => {
    try {
      // Prefer runtime-injected ENV; fallback to same-origin
      const v = (typeof window !== 'undefined' && (window as any).ENV?.NEXT_PUBLIC_API_URL) || ''
      return v && typeof v === 'string' && v.trim().length > 0 ? v.replace(/\/$/, '') : window.location.origin
    } catch {
      return typeof window !== 'undefined' ? window.location.origin : ''
    }
  }

  const refreshIntegrations = async () => {
    try {
      setIntLoading(true)
      setIntError(null)
      const tenantId = getTenantId()
      if (!tenantId) throw new Error('Missing tenant identity')
      const { data } = await client.query<{ getIntegrations: Integration[] }>({
        query: GET_INTEGRATIONS_QUERY,
        variables: { tenant_id: tenantId },
        fetchPolicy: 'network-only',
      })
      const onlyNeeded = (data.getIntegrations || []).filter((x) => {
        const key = (x.serviceName || '').toLowerCase()
        return PROVIDERS.includes(key as Provider)
      })
      const map: Record<string, Integration> = {}
      for (const it of onlyNeeded) {
        const key = (it.serviceName || '').toLowerCase()
        map[key] = it
      }
      setIntegrationMap(map)
    } catch (e) {
      console.error('Failed to load integrations', e)
      setIntError('Failed to load source connection status')
    } finally {
      setIntLoading(false)
    }
  }

  const startOAuth = async (provider: Provider) => {
    try {
      const api = getApiBase()
      const auth = token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null)
      let url = `${api}/oauth/silo/${provider}/start?redirect_to=${encodeURIComponent(window.location.href)}`
      if (provider === 'shopify') {
        const shop = window.prompt('Enter your Shopify shop domain (e.g., my-store or my-store.myshopify.com)')
        if (!shop) return
        url += `&shop=${encodeURIComponent(shop)}`
      }
      const res = await fetch(url, {
        method: 'GET',
        headers: {
          ...(auth ? { Authorization: `Bearer ${auth}` } : {}),
        },
      })
      if (!res.ok) throw new Error(`OAuth start failed: ${res.status}`)
      const data = await res.json().catch(() => null)
      const authorize = data?.authorize_url
      if (!authorize) throw new Error('Missing authorize_url from server')
      // Open provider consent in new tab for now
      window.open(authorize, '_blank', 'noopener')
      // Begin auto-polling status for ~30s (every 3s)
      if (!isPolling) {
        setIsPolling(true)
        // immediate refresh
        refreshIntegrations()
        pollIntervalRef.current = setInterval(() => {
          refreshIntegrations()
        }, 3000)
        pollTimeoutRef.current = setTimeout(() => {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
          pollIntervalRef.current = null
          setIsPolling(false)
        }, 30000)
      }
    } catch (e: any) {
      console.error('OAuth start error', e)
      setIntError(e?.message || 'OAuth start failed')
    }
  }

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const { data } = await client.query({
          query: LIST_REPOSITORY_ASSETS,
          variables: { limit: 24, include_download: false },
          fetchPolicy: 'network-only',
        })
        setAssets(data?.listRepositoryAssets || [])
      } catch (e) {
        console.error('Failed to load repository assets', e)
        setError('Failed to load knowledge assets')
      } finally {
        setLoading(false)
      }
    }
    load()
    // Also fetch source connection status
    refreshIntegrations()
    return () => {
      try { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current) } catch {}
      try { if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current) } catch {}
      pollIntervalRef.current = null
      pollTimeoutRef.current = null
      setIsPolling(false)
    }
  }, [client])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Knowledge Base Hub</h1>
          <p className="text-muted-foreground">Manage your uploaded files and knowledge sources</p>
        </div>
        <Button className="gap-2 glass-card glass-hover">
          <Upload className="h-4 w-4" />
          Upload File
        </Button>
      </div>

      {/* Connect Sources Section */}
      <Card className="glass-card">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base">Connect Sources</CardTitle>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" className="glass-button" onClick={refreshIntegrations} disabled={intLoading}>
                <RefreshCw className={`h-4 w-4 mr-2 ${intLoading ? 'animate-spin' : ''}`} />
                Refresh status
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {intError && (
            <div className="text-sm text-destructive">{intError}</div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {PROVIDERS.map((p) => {
              const status = integrationMap[p]?.status?.toLowerCase() || 'disconnected'
              const isConnected = status === 'connected'
              return (
                <div key={p} className="flex items-center justify-between gap-3 p-3 rounded-md bg-white/5 border border-white/10">
                  <div className="flex items-center gap-2">
                    <BrandAvatar name={PROVIDER_META[p].name} domain={PROVIDER_META[p].domain} size={24} />
                    <span className="capitalize">{PROVIDER_META[p].name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={isConnected ? 'default' : 'outline'} className="capitalize">
                      {status}
                    </Badge>
                    <Button size="sm" className="glass-button" variant={isConnected ? 'outline' : 'default'} onClick={() => startOAuth(p)} disabled={intLoading}>
                      {isConnected ? 'Reconnect' : 'Connect'}
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* Loading / Error States */}
      {loading && (
        <div className="flex items-center justify-center py-12 text-muted-foreground">Loading knowledge assets...</div>
      )}
      {error && !loading && (
        <Card className="text-center py-10 glass-card">
          <CardContent>
            <div className="text-destructive mb-4">{error}</div>
            <Button onClick={() => window.location.reload()} variant="outline">Retry</Button>
          </CardContent>
        </Card>
      )}

      {!loading && !error && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {assets.map((asset) => {
            const IconComponent = getFileIcon(asset.mimeType)
            const sizeMB = (asset.sizeBytes / (1024 * 1024)).toFixed(2) + ' MB'
            const uploaded = new Date(asset.createdAt).toLocaleDateString()
            return (
              <Card key={asset.assetId} className="glass-card glass-hover transition-all duration-300">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <IconComponent className="h-8 w-8 text-muted-foreground" />
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  </div>
                  <CardTitle className="text-base truncate" title={asset.filename}>
                    {asset.filename}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="text-sm text-muted-foreground space-y-1">
                    <div>Size: {sizeMB}</div>
                    <div>Uploaded: {uploaded}</div>
                    {asset.jobId && <div>Job: {asset.jobId}</div>}
                  </div>
                  <Button variant="outline" size="sm" className="w-full iridescent-subtle glass-hover bg-transparent">
                    View Metadata
                  </Button>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {!loading && !error && assets.length === 0 && (
        <Card className="text-center py-12 glass-card">
          <CardContent>
            <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium mb-2">No files uploaded yet</h3>
            <p className="text-muted-foreground mb-4">Upload your first file to start building your knowledge base</p>
            <Button className="gap-2 glass-card glass-hover">
              <Upload className="h-4 w-4" />
              Upload File
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
