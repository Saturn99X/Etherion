'use client'

import { useState, useEffect } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Settings, Plus, CheckCircle, XCircle, AlertCircle } from "lucide-react"
import { BrandAvatar } from "@/components/brand-avatar"
import { useApolloClient } from "@/components/apollo-provider";
import { useAuthStore } from "@/lib/stores/auth-store";
import { decodeJwt } from "@/lib/jwt";
import { GET_INTEGRATIONS_QUERY, CONNECT_INTEGRATION_MUTATION, TEST_INTEGRATION_MUTATION } from "@/lib/graphql-operations"

interface Integration {
  serviceName: string
  status: string
  lastConnected?: string
  errorMessage?: string
  capabilities: string[]
}

interface IntegrationCredentials {
  apiKey: string
  otherCredentials: string
}

interface CredentialCardProps {
  integration: Integration
  onConnect: (integration: Integration) => void
  onManage: (integration: Integration) => void
  onTest: (integration: Integration) => void
  testingIntegration: string | null
}

function CredentialCard({ integration, onConnect, onManage, onTest, testingIntegration }: CredentialCardProps) {
  const SERVICE_META: Record<string, { name: string; domain: string }> = {
    openai: { name: 'OpenAI', domain: 'openai.com' },
    anthropic: { name: 'Anthropic', domain: 'anthropic.com' },
    supabase: { name: 'Supabase', domain: 'supabase.com' },
    stripe: { name: 'Stripe', domain: 'stripe.com' },
    github: { name: 'GitHub', domain: 'github.com' },
    slack: { name: 'Slack', domain: 'slack.com' },
    jira: { name: 'Jira', domain: 'atlassian.com' },
    hubspot: { name: 'HubSpot', domain: 'hubspot.com' },
    linkedin: { name: 'LinkedIn', domain: 'linkedin.com' },
    notion: { name: 'Notion', domain: 'notion.so' },
    resend: { name: 'Resend', domain: 'resend.com' },
    shopify: { name: 'Shopify', domain: 'shopify.com' },
    twitter: { name: 'Twitter (X)', domain: 'x.com' },
    redfin: { name: 'Redfin', domain: 'redfin.com' },
    zillow: { name: 'Zillow', domain: 'zillow.com' },
  }
  const svcKey = integration.serviceName?.toLowerCase?.() || ''

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'connected':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'error':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'connecting':
        return <AlertCircle className="h-4 w-4 text-yellow-500" />
      default:
        return <XCircle className="h-4 w-4 text-gray-400" />
    }
  }

  const getStatusVariant = (status: string) => {
    switch (status.toLowerCase()) {
      case 'connected':
        return 'default'
      case 'error':
        return 'destructive'
      case 'connecting':
        return 'secondary'
      default:
        return 'outline'
    }
  }

  return (
    <Card className="glass-card hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <BrandAvatar
            name={SERVICE_META[svcKey]?.name || integration.serviceName}
            domain={SERVICE_META[svcKey]?.domain}
            size={40}
          />
          <div className="flex-1">
            <CardTitle className="text-base">{SERVICE_META[svcKey]?.name || integration.serviceName}</CardTitle>
            <p className="text-sm text-muted-foreground">
              {integration.errorMessage || `${integration.capabilities.length} capabilities`}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          {getStatusIcon(integration.status)}
          <Badge variant={getStatusVariant(integration.status)} className="w-fit">
            {integration.status}
          </Badge>
        </div>

        {integration.capabilities && integration.capabilities.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {integration.capabilities.slice(0, 2).map((capability, index) => (
              <span
                key={index}
                className="text-xs px-2 py-1 bg-secondary rounded-md text-secondary-foreground"
              >
                {capability}
              </span>
            ))}
            {integration.capabilities.length > 2 && (
              <span className="text-xs px-2 py-1 bg-secondary rounded-md text-secondary-foreground">
                +{integration.capabilities.length - 2}
              </span>
            )}
          </div>
        )}

        <div className="flex gap-2">
          <Button
            variant={integration.status === "connected" ? "outline" : "default"}
            size="sm"
            className="flex-1 gap-2 glass-button"
            onClick={() => (integration.status === "connected" ? onManage(integration) : onConnect(integration))}
          >
            {integration.status === "connected" ? (
              <>
                <Settings className="h-4 w-4" />
                Manage
              </>
            ) : (
              <>
                <Plus className="h-4 w-4" />
                Connect
              </>
            )}
          </Button>

          {integration.status === "connected" && (
            <Button
              variant="outline"
              size="sm"
              className="gap-2 glass-button"
              onClick={() => onTest(integration)}
              disabled={testingIntegration === integration.serviceName}
            >
              {testingIntegration === integration.serviceName ? 'Testing...' : 'Test'}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

interface CredentialFormModalProps {
  integration: Integration | null
  isOpen: boolean
  onClose: () => void
  onSave: (credentials: { apiKey: string; otherCredentials: string }) => void
}

function CredentialFormModal({ integration, isOpen, onClose, onSave }: CredentialFormModalProps) {
  const [apiKey, setApiKey] = useState("")
  const [otherCredentials, setOtherCredentials] = useState("")

  const handleSave = () => {
    onSave({ apiKey, otherCredentials })
    setApiKey("")
    setOtherCredentials("")
    onClose()
  }

  const handleCancel = () => {
    setApiKey("")
    setOtherCredentials("")
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md glass-card">
        <DialogHeader>
          <DialogTitle>{integration ? `Configure ${integration.serviceName}` : "Configure Integration"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="apiKey">API Key</Label>
            <Input
              id="apiKey"
              type="password"
              placeholder="Enter your API key..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="otherCredentials">Other Credentials</Label>
            <Textarea
              id="otherCredentials"
              placeholder="Enter additional credentials or configuration..."
              value={otherCredentials}
              onChange={(e) => setOtherCredentials(e.target.value)}
              rows={4}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={handleCancel} className="glass-button bg-transparent">
            Cancel
          </Button>
          <Button onClick={handleSave} className="glass-button">
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function IntegrationHub() {
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedIntegration, setSelectedIntegration] = useState<Integration | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [testingIntegration, setTestingIntegration] = useState<string | null>(null)
  const client = useApolloClient();
  const { token } = useAuthStore();

  const getTenantId = (): number | null => {
    try {
      const t = token || (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null);
      if (!t) return null;
      const payload = decodeJwt(t);
      const tid = (payload && ((payload as any).tenant_id ?? (payload as any).tenantId)) as number | string | undefined;
      if (!tid) return null;
      const n = Number(tid);
      return Number.isFinite(n) ? n : null;
    } catch {
      return null;
    }
  }
  useEffect(() => {
    fetchIntegrations()
  }, [])

  const fetchIntegrations = async () => {
    try {
      setLoading(true)
      setError(null)

      const tenantId = getTenantId();
      if (!tenantId) {
        throw new Error('Missing tenant identity');
      }
      const { data } = await client.query({
        query: GET_INTEGRATIONS_QUERY,
        variables: { tenant_id: tenantId }
      })

      setIntegrations(data.getIntegrations)
    } catch (error) {
      console.error('Failed to fetch integrations:', error)
      setError('Failed to load integrations')
    } finally {
      setLoading(false)
    }
  }

  const handleConnect = (integration: Integration) => {
    setSelectedIntegration(integration)
    setIsModalOpen(true)
  }

  const handleManage = (integration: Integration) => {
    setSelectedIntegration(integration)
    setIsModalOpen(true)
  }

  const handleSave = async (credentials: IntegrationCredentials) => {
    if (!selectedIntegration) return

    try {
      const { data } = await client.mutate({
        mutation: CONNECT_INTEGRATION_MUTATION,
        variables: {
          service_name: selectedIntegration.serviceName,
          credentials: JSON.stringify({
            api_key: credentials.apiKey,
            other_credentials: credentials.otherCredentials
          })
        }
      })

      // Update local state with new status
      updateIntegrationStatus(data.connectIntegration)
      setIsModalOpen(false)
      setSelectedIntegration(null)
    } catch (error) {
      console.error('Failed to connect integration:', error)
      setError('Failed to connect integration')
    }
  }

  const handleTest = async (integration: Integration) => {
    try {
      setTestingIntegration(integration.serviceName)

      const { data } = await client.mutate({
        mutation: TEST_INTEGRATION_MUTATION,
        variables: { service_name: integration.serviceName }
      })

      if (data.testIntegration.success) {
        // Update integration status in local state
        updateIntegrationStatus({
          serviceName: integration.serviceName,
          status: "connected"
        })
        console.log('Integration test successful:', data.testIntegration.testResult)
      } else {
        console.error('Integration test failed:', data.testIntegration.errorMessage)
      }
    } catch (error) {
      console.error('Failed to test integration:', error)
    } finally {
      setTestingIntegration(null)
    }
  }

  const updateIntegrationStatus = (statusUpdate: { serviceName: string; status: string; errorMessage?: string }) => {
    setIntegrations((prev) =>
      prev.map((integration) =>
        integration.serviceName === statusUpdate.serviceName
          ? { ...integration, status: statusUpdate.status, errorMessage: statusUpdate.errorMessage }
          : integration
      )
    )
  }

  if (loading) {
    return (
      <div className="space-y-6 glass-container">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Integrations Hub</h1>
            <p className="text-muted-foreground">Connect and manage your third-party services</p>
          </div>
        </div>
        <div className="flex items-center justify-center py-12">
          <div className="text-muted-foreground">Loading integrations...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6 glass-container">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Integrations Hub</h1>
            <p className="text-muted-foreground">Connect and manage your third-party services</p>
          </div>
        </div>
        <Card className="text-center py-12">
          <CardContent>
            <div className="text-destructive mb-4">{error}</div>
            <Button onClick={fetchIntegrations} variant="outline">
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6 glass-container">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Integrations Hub</h1>
          <p className="text-muted-foreground">Connect and manage your third-party services</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {integrations.map((integration) => (
          <CredentialCard
            key={integration.serviceName}
            integration={integration}
            onConnect={handleConnect}
            onManage={handleManage}
            onTest={handleTest}
            testingIntegration={testingIntegration}
          />
        ))}
      </div>

      <CredentialFormModal
        integration={selectedIntegration}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSave={handleSave}
      />
    </div>
  )
}
