"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Plus, Edit, Trash2, TrendingUp, Calendar, Target } from "lucide-react"
import { useApolloClient } from "@/components/apollo-provider";
import { GET_TONE_PROFILES_QUERY, CREATE_TONE_PROFILE_MUTATION, APPLY_TONE_PROFILE_MUTATION } from "@/lib/graphql-operations"

interface ToneProfile {
  id: string
  name: string
  type: string
  description: string
  usageCount: number
  lastUsed?: string
  effectiveness?: number
}

export function ToneOfVoiceLibrary() {
  const [profiles, setProfiles] = useState<ToneProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [applyingProfile, setApplyingProfile] = useState<string | null>(null)
  const client = useApolloClient();
  useEffect(() => {
    fetchToneProfiles()
  }, [])

  const fetchToneProfiles = async () => {
    try {
      setLoading(true)
      setError(null)

      const { data } = await client.query({
        query: GET_TONE_PROFILES_QUERY,
        variables: { user_id: 1 } // TODO: Get actual user_id from auth context
      })

      setProfiles((data as any).getToneProfiles)
    } catch (error) {
      console.error('Failed to fetch tone profiles:', error)
      setError('Failed to load tone profiles')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateProfile = async () => {
    // TODO: Open create profile modal
    console.log("Create new profile clicked")
  }

  const handleEditProfile = (profile: ToneProfile) => {
    // TODO: Open edit profile modal
    console.log("Edit profile:", profile.name)
  }

  const handleDeleteProfile = async (profile: ToneProfile) => {
    // TODO: Implement delete functionality
    console.log("Delete profile:", profile.name)
  }

  const handleApplyProfile = async (profile: ToneProfile) => {
    try {
      setApplyingProfile(profile.id)

      await client.mutate({
        mutation: APPLY_TONE_PROFILE_MUTATION,
        variables: {
          profile_id: profile.id,
          goal_id: "current-goal" // TODO: Get current goal ID from context
        }
      })

      console.log(`Applied tone profile: ${profile.name}`)
    } catch (error) {
      console.error('Failed to apply tone profile:', error)
      setError('Failed to apply tone profile')
    } finally {
      setApplyingProfile(null)
    }
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never'
    return new Date(dateString).toLocaleDateString()
  }

  const getEffectivenessColor = (effectiveness?: number) => {
    if (!effectiveness) return 'text-muted-foreground'
    if (effectiveness >= 0.8) return 'text-green-600'
    if (effectiveness >= 0.6) return 'text-yellow-600'
    return 'text-red-600'
  }

  const getEffectivenessIcon = (effectiveness?: number) => {
    if (!effectiveness) return null
    if (effectiveness >= 0.8) return <TrendingUp className="h-4 w-4 text-green-500" />
    if (effectiveness >= 0.6) return <Target className="h-4 w-4 text-yellow-500" />
    return <Target className="h-4 w-4 text-red-500" />
  }

  if (loading) {
    return (
      <div className="container mx-auto p-6 space-y-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-2">
            <h1 className="text-3xl font-bold text-foreground">Tone of Voice Library</h1>
            <p className="text-muted-foreground">Manage the tone profiles that define how your AI agents communicate.</p>
          </div>
        </div>
        <div className="flex items-center justify-center py-12">
          <div className="text-muted-foreground">Loading tone profiles...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="container mx-auto p-6 space-y-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-2">
            <h1 className="text-3xl font-bold text-foreground">Tone of Voice Library</h1>
            <p className="text-muted-foreground">Manage the tone profiles that define how your AI agents communicate.</p>
          </div>
        </div>
        <Card className="text-center py-12">
          <CardContent>
            <div className="text-destructive mb-4">{error}</div>
            <Button onClick={fetchToneProfiles} variant="outline">
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="container mx-auto p-6 space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold text-foreground">Tone of Voice Library</h1>
          <p className="text-muted-foreground">Manage the tone profiles that define how your AI agents communicate.</p>
        </div>
        <Button className="glass-button" onClick={handleCreateProfile}>
          <Plus className="w-4 h-4 mr-2" />
          Create New Profile
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {profiles.map((profile) => (
          <Card key={profile.id} className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">{profile.name}</CardTitle>
                <Badge variant={profile.type === "system_default" ? "default" : "secondary"}>
                  {profile.type === "system_default" ? "System Default" : "User Created"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <CardDescription className="text-sm leading-relaxed">{profile.description}</CardDescription>

              <div className="space-y-2 text-sm text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4" />
                  <span>Usage: {profile.usageCount} times</span>
                </div>

                {profile.lastUsed && (
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4" />
                    <span>Last used: {formatDate(profile.lastUsed)}</span>
                  </div>
                )}

                {profile.effectiveness !== undefined && (
                  <div className="flex items-center gap-2">
                    {getEffectivenessIcon(profile.effectiveness)}
                    <span className={getEffectivenessColor(profile.effectiveness)}>
                      Effectiveness: {(profile.effectiveness * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
              </div>
            </CardContent>
            <CardFooter className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="flex-1"
                onClick={() => handleEditProfile(profile)}
              >
                <Edit className="w-4 h-4 mr-2" />
                Edit
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="flex-1"
                onClick={() => handleDeleteProfile(profile)}
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
              <Button
                variant="default"
                size="sm"
                className="flex-1"
                onClick={() => handleApplyProfile(profile)}
                disabled={applyingProfile === profile.id}
              >
                {applyingProfile === profile.id ? 'Applying...' : 'Apply'}
              </Button>
            </CardFooter>
          </Card>
        ))}
      </div>

      {profiles.length === 0 && (
        <Card className="text-center py-12">
          <CardContent>
            <div className="text-muted-foreground mb-4">No tone profiles found</div>
            <Button className="glass-button" onClick={handleCreateProfile}>
              <Plus className="w-4 h-4 mr-2" />
              Create Your First Profile
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
