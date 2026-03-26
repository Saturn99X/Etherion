"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Key,
  Plus,
  Edit,
  Trash2,
  Eye,
  EyeOff,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  Shield,
  RefreshCw,
  BookOpen
} from "lucide-react"
import { useApolloClient } from "@/components/apollo-provider";
import { MANAGE_MCP_CREDENTIALS_MUTATION, TEST_MCP_TOOL_MUTATION, GET_INTEGRATIONS_QUERY, DISCONNECT_INTEGRATION_MUTATION } from "@/lib/graphql-operations"
import { useAuthStore } from "@/lib/stores/auth-store";
import { decodeJwt } from "@/lib/jwt";
import { useRouter } from "next/navigation"

interface CredentialField {
  name: string
  type: 'text' | 'password' | 'number' | 'textarea'
  required: boolean
  description: string
  validation?: string
  placeholder?: string
}

interface SetupStep {
  title: string
  instructions: string[]
}

interface SetupGuide {
  title: string
  steps: SetupStep[]
}

interface CredentialSchema {
  toolName: string
  serviceName: string
  description: string
  fields: CredentialField[]
  capabilities: string[]
  setupGuide?: SetupGuide
}

const CREDENTIAL_SCHEMAS: Record<string, CredentialSchema> = {
  mcp_slack: {
    toolName: "mcp_slack",
    serviceName: "Slack",
    description: "Send messages and interact with Slack workspaces (OAuth-only)",
    capabilities: ["send_message", "read_channel", "file_upload", "create_channel"],
    setupGuide: {
      title: "How to Set Up Slack Integration",
      steps: [
        {
          title: "Create a Slack App",
          instructions: [
            "1. Go to https://api.slack.com/apps",
            "2. Click 'Create New App'",
            "3. Choose 'From scratch' and give it a name",
            "4. Select your workspace"
          ]
        },
        {
          title: "Configure Bot Permissions",
          instructions: [
            "1. In your app settings, go to 'OAuth & Permissions'",
            "2. Add these Bot Token Scopes:",
            "   • channels:history - View messages and files",
            "   • channels:read - Access public channels",
            "   • chat:write - Send messages",
            "   • files:read - Access files",
            "   • files:write - Upload files"
          ]
        },
        {
          title: "Install the App",
          instructions: [
            "1. Click 'Install to Workspace'",
            "2. Authorize the app installation",
            "3. Copy the 'Bot User OAuth Token' (starts with xoxb-)"
          ]
        },
        {
          title: "Invite Bot to Channels",
          instructions: [
            "1. In Slack, type '/invite @YourBotName' in channels you want to access",
            "2. The bot needs to be in channels to send messages"
          ]
        }
      ]
    },
    fields: []
  },
  mcp_email: {
    toolName: "mcp_email",
    serviceName: "Email Service",
    description: "Send and manage emails through various providers",
    capabilities: ["send_email", "list_emails", "search_emails", "email_templates"],
    setupGuide: {
      title: "How to Set Up Email Integration",
      steps: [
        {
          title: "Choose an Email Provider",
          instructions: [
            "1. Select one of the supported providers:",
            "   • Resend (Recommended) - Modern email API",
            "   • SendGrid - Popular email service",
            "   • Mailgun - Reliable email delivery",
            "   • Amazon SES - Cost-effective for high volume"
          ]
        },
        {
          title: "Sign Up for Resend (Recommended)",
          instructions: [
            "1. Go to https://resend.com/",
            "2. Click 'Sign Up' and create an account",
            "3. Verify your email address",
            "4. Go to 'API Keys' in your dashboard",
            "5. Click 'Create API Key'",
            "6. Copy the API key (starts with 're_')"
          ]
        },
        {
          title: "For SendGrid Setup",
          instructions: [
            "1. Go to https://sendgrid.com/",
            "2. Create account and verify email",
            "3. Go to 'Settings' → 'API Keys'",
            "4. Click 'Create API Key'",
            "5. Choose a name and select 'Full Access'",
            "6. Copy the generated API key"
          ]
        },
        {
          title: "Domain Verification (Recommended)",
          instructions: [
            "1. In your email provider dashboard:",
            "   • Resend: Go to 'Domains' → 'Add Domain'",
            "   • SendGrid: Go to 'Settings' → 'Sender Authentication'",
            "2. Add your domain (e.g., yourdomain.com)",
            "3. Copy the DNS records provided",
            "4. Add these records to your domain's DNS settings",
            "5. Wait for verification (can take up to 24 hours)"
          ]
        }
      ]
    },
    fields: [
      {
        name: 'api_key',
        type: 'password',
        required: true,
        description: 'Email service API key (SendGrid, Mailgun, etc.)',
        placeholder: 'SG.xxxxxxxx...'
      },
      {
        name: 'domain',
        type: 'text',
        required: false,
        description: 'Verified sending domain',
        placeholder: 'yourdomain.com'
      },
      {
        name: 'from_email',
        type: 'text',
        required: true,
        description: 'Default sender email address',
        placeholder: 'noreply@yourdomain.com'
      }
    ]
  },
  mcp_jira: {
    toolName: "mcp_jira",
    serviceName: "Jira",
    description: "Manage Jira tickets and project tracking (OAuth-only)",
    capabilities: ["create_ticket", "update_ticket", "get_ticket", "search_tickets", "project_management"],
    setupGuide: {
      title: "How to Set Up Jira Integration",
      steps: [
        {
          title: "Get Your Jira Site URL",
          instructions: [
            "1. Go to your Jira instance (e.g., https://yourcompany.atlassian.net)",
            "2. Note your site URL (everything before '.atlassian.net')"
          ]
        },
        {
          title: "Create an API Token",
          instructions: [
            "1. Go to https://id.atlassian.com/manage-profile/security/api-tokens",
            "2. Click 'Create API token'",
            "3. Give it a name (e.g., 'Etherion Integration')",
            "4. Click 'Create' and copy the token immediately",
            "5. ⚠️ Store it safely - you won't see it again!"
          ]
        },
        {
          title: "Gather Required Information",
          instructions: [
            "1. Your Jira site URL (e.g., 'yourcompany')",
            "2. Your email address (same as login)",
            "3. The API token you just created",
            "4. Make sure you have access to the projects you want to manage"
          ]
        }
      ]
    },
    fields: []
  },
  mcp_hubspot: {
    toolName: "mcp_hubspot",
    serviceName: "HubSpot",
    description: "Manage HubSpot contacts, deals, and marketing campaigns (OAuth-only)",
    capabilities: ["create_contact", "update_contact", "get_contact", "create_deal", "crm_management"],
    fields: []
  },
  mcp_linkedin: {
    toolName: "mcp_linkedin",
    serviceName: "LinkedIn",
    description: "Access LinkedIn profiles, connections, and company data",
    capabilities: ["get_profile", "get_connections", "search_companies", "post_updates"],
    fields: [
      {
        name: 'access_token',
        type: 'password',
        required: true,
        description: 'LinkedIn access token from LinkedIn Developer Console',
        placeholder: 'AQX...'
      },
      {
        name: 'refresh_token',
        type: 'password',
        required: false,
        description: 'Refresh token for token renewal',
        placeholder: 'AQQ...'
      },
      {
        name: 'expires_at',
        type: 'text',
        required: false,
        description: 'Token expiration timestamp',
        placeholder: '2025-01-01T00:00:00Z'
      }
    ]
  },
  mcp_notion: {
    toolName: "mcp_notion",
    serviceName: "Notion",
    description: "Create, read, and update Notion pages and databases (OAuth-only)",
    capabilities: ["create_page", "update_page", "query_database", "search_pages", "workspace_management"],
    fields: []
  },
  mcp_resend: {
    toolName: "mcp_resend",
    serviceName: "Resend",
    description: "Send transactional emails through Resend API",
    capabilities: ["send_email", "get_email_status", "email_templates", "domain_management"],
    fields: [
      {
        name: 'api_key',
        type: 'password',
        required: true,
        description: 'Resend API key from https://resend.com/api-keys',
        placeholder: 're_...'
      },
      {
        name: 'domain_id',
        type: 'text',
        required: false,
        description: 'Verified domain ID for sending emails',
        placeholder: 'domain-id-here'
      }
    ]
  },
  mcp_shopify: {
    toolName: "mcp_shopify",
    serviceName: "Shopify",
    description: "Access Shopify store data, orders, and products (OAuth-only)",
    capabilities: ["get_orders", "get_products", "update_order", "create_product", "inventory_management"],
    fields: []
  },
  mcp_twitter: {
    toolName: "mcp_twitter",
    serviceName: "Twitter/X",
    description: "Access Twitter/X data and post updates",
    capabilities: ["post_tweet", "get_tweets", "search_tweets", "get_user", "trends"],
    setupGuide: {
      title: "How to Set Up Twitter/X Integration",
      steps: [
        {
          title: "⚠️ Important: Twitter API Changes",
          instructions: [
            "Twitter API v2 has significantly changed access levels:",
            "• Free tier: Very limited (1,500 posts/month, 500 reads/month)",
            "• Basic tier: $100/month - 50,000 posts, 10,000 reads",
            "• Pro tier: $5,000/month - Higher limits",
            "Consider if you really need Twitter integration due to costs."
          ]
        },
        {
          title: "Create a Twitter Developer Account",
          instructions: [
            "1. Go to https://developer.twitter.com/",
            "2. Click 'Apply for access' or sign in",
            "3. Apply for a developer account if you don't have one",
            "4. Wait for approval (can take several days)"
          ]
        },
        {
          title: "Create a Twitter App",
          instructions: [
            "1. In Twitter Developer Portal, click 'Create App'",
            "2. Choose your use case and fill out the form",
            "3. Get your API Key and API Secret",
            "4. Generate Access Token and Access Token Secret",
            "5. ⚠️ Copy all credentials immediately - they're shown once!"
          ]
        },
        {
          title: "Configure App Permissions",
          instructions: [
            "1. In your app settings, go to 'Permissions'",
            "2. Set access to 'Read and Write' for posting",
            "3. Add these scopes:",
            "   • tweet.read - Read tweets",
            "   • tweet.write - Post tweets",
            "   • users.read - Read user info"
          ]
        },
        {
          title: "Consider Alternatives",
          instructions: [
            "Due to high costs, consider:",
            "• Using webhooks instead of polling",
            "• Implementing rate limiting",
            "• Using Twitter's embedded widgets",
            "• Alternative social media platforms"
          ]
        }
      ]
    },
    fields: [
      {
        name: 'api_key',
        type: 'password',
        required: true,
        description: 'Twitter API key',
        placeholder: 'API_KEY'
      },
      {
        name: 'api_secret',
        type: 'password',
        required: true,
        description: 'Twitter API secret',
        placeholder: 'API_SECRET'
      },
      {
        name: 'access_token',
        type: 'password',
        required: true,
        description: 'Twitter access token',
        placeholder: 'ACCESS_TOKEN'
      },
      {
        name: 'access_token_secret',
        type: 'password',
        required: true,
        description: 'Twitter access token secret',
        placeholder: 'ACCESS_TOKEN_SECRET'
      },
      {
        name: 'bearer_token',
        type: 'password',
        required: false,
        description: 'Bearer token (optional, for read-only access)',
        placeholder: 'BEARER_TOKEN'
      }
    ]
  },
  mcp_redfin: {
    toolName: "mcp_redfin",
    serviceName: "Redfin",
    description: "Access real estate data from Redfin",
    capabilities: ["search_properties", "get_property_details", "get_market_data", "real_estate_trends"],
    setupGuide: {
      title: "How to Set Up Redfin Integration (via RapidAPI)",
      steps: [
        {
          title: "Sign Up for RapidAPI",
          instructions: [
            "1. Go to https://rapidapi.com/",
            "2. Create a free account",
            "3. Verify your email address"
          ]
        },
        {
          title: "Subscribe to Redfin API",
          instructions: [
            "1. Search for 'Redfin' in RapidAPI Hub",
            "2. Find 'Realty in US' API",
            "3. Click 'Subscribe to Test' (free tier)",
            "4. Copy the 'X-RapidAPI-Key' from your dashboard"
          ]
        },
        {
          title: "⚠️ API Limitations",
          instructions: [
            "• Free tier: Very limited requests per month",
            "• Consider upgrading for production use",
            "• Real estate data is often restricted",
            "• Alternative: Use web scraping (less reliable)"
          ]
        }
      ]
    },
    fields: [
      {
        name: 'api_key',
        type: 'password',
        required: true,
        description: 'RapidAPI Key from https://rapidapi.com/',
        placeholder: 'YOUR_RAPIDAPI_KEY'
      },
      {
        name: 'base_url',
        type: 'text',
        required: false,
        description: 'Custom API base URL (optional)',
        placeholder: 'https://api.redfin.com'
      }
    ]
  },
  mcp_zillow: {
    toolName: "mcp_zillow",
    serviceName: "Zillow",
    description: "Access real estate data from Zillow",
    capabilities: ["search_properties", "get_property_details", "get_zestimate", "market_analysis"],
    setupGuide: {
      title: "How to Set Up Zillow Integration (via RapidAPI)",
      steps: [
        {
          title: "Sign Up for RapidAPI",
          instructions: [
            "1. Go to https://rapidapi.com/",
            "2. Create a free account",
            "3. Verify your email address"
          ]
        },
        {
          title: "Subscribe to Zillow API",
          instructions: [
            "1. Search for 'Zillow' in RapidAPI Hub",
            "2. Find 'Zillow API' or similar real estate API",
            "3. Click 'Subscribe to Test' (free tier)",
            "4. Copy the 'X-RapidAPI-Key' from your dashboard"
          ]
        },
        {
          title: "⚠️ Important Notes",
          instructions: [
            "• Zillow doesn't provide free public API",
            "• RapidAPI provides aggregated real estate data",
            "• Data accuracy may vary",
            "• Consider Zillow's official partnerships for production"
          ]
        }
      ]
    },
    fields: [
      {
        name: 'api_key',
        type: 'password',
        required: true,
        description: 'RapidAPI Key from https://rapidapi.com/',
        placeholder: 'YOUR_RAPIDAPI_KEY'
      },
      {
        name: 'base_url',
        type: 'text',
        required: false,
        description: 'Custom API base URL (optional)',
        placeholder: 'https://api.zillow.com'
      }
    ]
  },
}

interface CredentialManagerProps {
  toolName?: string
  onClose?: () => void
}

export function CredentialManager({ toolName, onClose }: CredentialManagerProps) {
  const [selectedTool, setSelectedTool] = useState<string>(toolName || "")
  const [credentials, setCredentials] = useState<Record<string, string>>({})
  const [visiblePasswords, setVisiblePasswords] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<any>(null)
  const [permissionTier, setPermissionTier] = useState<"minimal" | "full">("minimal")
  const router = useRouter()
  const client = useApolloClient();
  const schema = selectedTool ? CREDENTIAL_SCHEMAS[selectedTool] : null
  const { token } = useAuthStore()
  const oauthProviders = new Set(["slack","google","jira","hubspot","notion","shopify"]) // OAuth-backed per Step 4
  const providerKey = (selectedTool || "").replace("mcp_","")
  const isOauthBacked = oauthProviders.has(providerKey)
  const [connectionStatus, setConnectionStatus] = useState<"unknown" | "connected" | "disconnected" | "error">("unknown")

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
    const loadConn = async () => {
      if (!isOauthBacked) { setConnectionStatus("unknown"); return }
      const tenantId = getTenantId();
      if (!tenantId) { setConnectionStatus("unknown"); return }
      try {
        const { data } = await client.query({ query: GET_INTEGRATIONS_QUERY, variables: { tenant_id: tenantId } })
        const list = (data as any)?.getIntegrations || []
        const match = list.find((i: any) => (i.serviceName || '').toLowerCase() === providerKey)
        if (match?.status?.toLowerCase() === 'connected') setConnectionStatus("connected")
        else if (match?.status) setConnectionStatus("disconnected")
        else setConnectionStatus("unknown")
      } catch {
        setConnectionStatus("error")
      }
    }
    loadConn()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTool, providerKey, isOauthBacked])

  const connectViaOAuth = async () => {
    try {
      setError(null)
      const tenantId = getTenantId();
      if (!tenantId) { setError('Missing tenant identity'); return }
      const resp = await fetch(`/oauth/silo/${providerKey}/start?tenant_id=${tenantId}&tier=${permissionTier}`)
      const data = await resp.json()
      const url = data.authorize_url
      if (url) {
        const popup = window.open(url, "oauth", "width=500,height=700")
        const listener = (event: MessageEvent) => {
          if (event.data && event.data.type === 'oauth_connected') {
            window.removeEventListener('message', listener)
            setSuccess(`${schema?.serviceName || providerKey} connected`)
            setConnectionStatus("connected")
            popup?.close()
          }
        }
        window.addEventListener('message', listener)
      } else {
        setError('Authorization URL unavailable')
      }
    } catch (e) {
      setError('Failed to start OAuth flow')
    }
  }

  // Disconnect OAuth integration for current provider
  const disconnectOAuth = async () => {
    try {
      setError(null)
      const resp = await client.mutate({
        mutation: DISCONNECT_INTEGRATION_MUTATION,
        variables: { service_name: providerKey },
      })
      if ((resp.data as any)?.disconnectIntegration) {
        setSuccess(`${schema?.serviceName || providerKey} disconnected`)
        setConnectionStatus("disconnected")
      } else {
        setError('Failed to disconnect integration')
      }
    } catch (e) {
      setError('Failed to disconnect integration')
    }
  }

  const handleCredentialChange = (fieldName: string, value: string) => {
    setCredentials(prev => ({ ...prev, [fieldName]: value }))
  }

  const togglePasswordVisibility = (fieldName: string) => {
    setVisiblePasswords(prev => ({ ...prev, [fieldName]: !prev[fieldName] }))
  }

  const handleSaveCredentials = async () => {
    if (!schema || !selectedTool) return

    try {
      setLoading(true)
      setError(null)

      // Validate required fields
      const missingFields = schema.fields
        .filter(field => field.required && !credentials[field.name]?.trim())
        .map(field => field.name)

      if (missingFields.length > 0) {
        setError(`Missing required fields: ${missingFields.join(', ')}`)
        return
      }

      // Validate field formats
      for (const field of schema.fields) {
        const value = credentials[field.name]?.trim()
        if (value && field.validation) {
          const regex = new RegExp(field.validation)
          if (!regex.test(value)) {
            setError(`Invalid format for ${field.name}`)
            return
          }
        }
      }

      await client.mutate({
        mutation: MANAGE_MCP_CREDENTIALS_MUTATION,
        variables: {
          tool_name: selectedTool,
          credentials: JSON.stringify(credentials)
        }
      })

      setSuccess(`Credentials saved successfully for ${schema.serviceName}`)
      setError(null)
    } catch (error) {
      console.error('Failed to save credentials:', error)
      setError('Failed to save credentials')
      setSuccess(null)
    } finally {
      setLoading(false)
    }
  }

  const handleTestCredentials = async () => {
    if (!selectedTool) return

    try {
      setTesting(true)
      setError(null)
      setTestResult(null)

      const { data } = await client.mutate({
        mutation: TEST_MCP_TOOL_MUTATION,
        variables: { tool_name: selectedTool }
      })

      setTestResult((data as any).testMCPTool)
    } catch (error) {
      console.error('Failed to test MCP tool:', error)
      setError('Failed to test credentials')
      setTestResult(null)
    } finally {
      setTesting(false)
    }
  }

  const handleLoadCredentials = async () => {
    // TODO: Implement loading existing credentials from backend
    console.log('Loading existing credentials for', selectedTool)
  }

  const getCredentialValue = (fieldName: string) => {
    return credentials[fieldName] || ''
  }

  const isPasswordField = (field: CredentialField) => field.type === 'password'

  if (!selectedTool || !schema) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold">Credential Manager</h2>
            <p className="text-muted-foreground">Manage secure credentials for MCP tools</p>
          </div>
          {onClose && (
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          )}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Select MCP Tool</CardTitle>
            <CardDescription>Choose a tool to manage its credentials</CardDescription>
          </CardHeader>
          <CardContent>
            <Select value={selectedTool} onValueChange={setSelectedTool}>
              <SelectTrigger>
                <SelectValue placeholder="Select an MCP tool..." />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(CREDENTIAL_SCHEMAS).map(([key, schema]) => (
                  <SelectItem key={key} value={key}>
                    <div className="flex items-center gap-2">
                      <span>{schema.serviceName}</span>
                      <Badge variant="outline" className="text-xs">
                        {schema.capabilities.length} capabilities
                      </Badge>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Credential Manager</h2>
          <p className="text-muted-foreground">Manage secure credentials for {schema.serviceName}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setSelectedTool("")}>
            Change Tool
          </Button>
          {onClose && (
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          )}
        </div>
      </div>

      <Tabs defaultValue="setup" className="space-y-4">
        <TabsList>
          <TabsTrigger value="setup">Setup Guide</TabsTrigger>
          <TabsTrigger value="credentials">Credentials</TabsTrigger>
          <TabsTrigger value="capabilities">Capabilities</TabsTrigger>
          <TabsTrigger value="testing">Testing</TabsTrigger>
        </TabsList>

        <TabsContent value="setup" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="h-5 w-5" />
                {schema.setupGuide?.title || 'Setup Guide'}
              </CardTitle>
              <CardDescription>
                Step-by-step instructions to set up {schema.serviceName} integration
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {schema.setupGuide?.steps.map((step, index) => (
                <div key={index} className="space-y-3">
                  <h4 className="font-semibold text-sm flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">
                      {index + 1}
                    </div>
                    {step.title}
                  </h4>
                  <div className="ml-8 space-y-2">
                    {step.instructions.map((instruction, idx) => (
                      <p key={idx} className="text-sm text-muted-foreground leading-relaxed">
                        {instruction}
                      </p>
                    ))}
                  </div>
                </div>
              ))}

              {(!schema.setupGuide || schema.setupGuide.steps.length === 0) && (
                <div className="text-center py-8 text-muted-foreground">
                  <BookOpen className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No setup guide available for this tool yet.</p>
                  <p className="text-sm mt-2">Please refer to the official documentation.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="credentials" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Key className="h-5 w-5" />
                {schema.serviceName} Credentials
              </CardTitle>
              <CardDescription>
                Configure the credentials needed to connect to {schema.serviceName}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="permissionTier" className="flex items-center gap-2">
                  Permissions
                </Label>
                <Select value={permissionTier} onValueChange={(v) => setPermissionTier(v as any)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select permission level" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="minimal">Minimal (read or narrow write)</SelectItem>
                    <SelectItem value="full">Full (expanded capabilities)</SelectItem>
                  </SelectContent>
                </Select>
                {permissionTier === "full" && (
                  <Alert>
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>Full permissions will request additional scopes during re‑consent.</AlertDescription>
                  </Alert>
                )}
              </div>

              {!isOauthBacked && schema.fields.map((field) => (
                <div key={field.name} className="space-y-2">
                  <Label htmlFor={field.name} className="flex items-center gap-2">
                    {field.name}
                    {field.required && <span className="text-destructive">*</span>}
                  </Label>
                  <div className="relative">
                    {field.type === 'textarea' ? (
                      <Textarea
                        id={field.name}
                        placeholder={field.placeholder}
                        value={getCredentialValue(field.name)}
                        onChange={(e) => handleCredentialChange(field.name, e.target.value)}
                        className="pr-10"
                      />
                    ) : (
                      <Input
                        id={field.name}
                        type={isPasswordField(field) && !visiblePasswords[field.name] ? 'password' : 'text'}
                        placeholder={field.placeholder}
                        value={getCredentialValue(field.name)}
                        onChange={(e) => handleCredentialChange(field.name, e.target.value)}
                        className="pr-10"
                      />
                    )}
                    {isPasswordField(field) && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                        onClick={() => togglePasswordVisibility(field.name)}
                      >
                        {visiblePasswords[field.name] ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">{field.description}</p>
                </div>
              ))}
              {isOauthBacked && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">Connection status:</span>
                    <Badge variant={connectionStatus === 'connected' ? 'default' : connectionStatus === 'error' ? 'destructive' : 'outline'}>
                      {connectionStatus}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">This provider uses OAuth. Use Connect to grant access. Manual keys are hidden.</p>
                </div>
              )}

              {error && (
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              {success && (
                <Alert>
                  <CheckCircle className="h-4 w-4" />
                  <AlertDescription>{success}</AlertDescription>
                </Alert>
              )}
            </CardContent>
            <CardFooter className="flex gap-2">
              {!isOauthBacked && (
                <Button onClick={handleSaveCredentials} disabled={loading}>
                  {loading ? (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Shield className="mr-2 h-4 w-4" />
                      Save Credentials
                    </>
                  )}
                </Button>
              )}
              {isOauthBacked && (
                <>
                  <div className="flex gap-2">
                    <Button onClick={connectViaOAuth}>
                      {connectionStatus === 'connected' ? 'Reconnect' : 'Connect via OAuth'}
                    </Button>
                    {connectionStatus === 'connected' && (
                      <Button variant="outline" onClick={disconnectOAuth}>
                        Disconnect
                      </Button>
                    )}
                  </div>
                </>
              )}
              <Button variant="outline" onClick={handleLoadCredentials}>
                Load Existing
              </Button>
            </CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="capabilities" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Available Capabilities</CardTitle>
              <CardDescription>
                {schema.serviceName} provides {schema.capabilities.length} capabilities
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {schema.capabilities.map((capability, index) => (
                  <Badge key={index} variant="outline" className="justify-center py-1">
                    {capability.replace('_', ' ')}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="testing" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Test Connection</CardTitle>
              <CardDescription>
                Test the connection to {schema.serviceName} using current credentials
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {testResult && (
                <Alert variant={testResult.success ? "default" : "destructive"}>
                  {testResult.success ? (
                    <CheckCircle className="h-4 w-4" />
                  ) : (
                    <XCircle className="h-4 w-4" />
                  )}
                  <AlertDescription>{testResult.testResult}</AlertDescription>
                </Alert>
              )}

              {error && !testResult && (
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
            </CardContent>
            <CardFooter>
              <Button
                onClick={handleTestCredentials}
                disabled={testing}
                className="w-full"
              >
                {testing ? (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                    Testing Connection...
                  </>
                ) : (
                  <>
                    <CheckCircle className="mr-2 h-4 w-4" />
                    Test Connection
                  </>
                )}
              </Button>
            </CardFooter>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
