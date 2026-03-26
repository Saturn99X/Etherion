"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Download, RefreshCw, Image as ImageIcon, FileText } from "lucide-react"
import { useApolloClient } from "@/components/apollo-provider";
import { LIST_REPOSITORY_ASSETS } from "@/lib/graphql-operations"
import { useToast } from "@/hooks/use-toast"

interface RepoAsset {
  assetId: string
  jobId?: string | null
  filename: string
  mimeType: string
  sizeBytes: number
  gcsUri: string
  createdAt: string
  downloadUrl?: string | null
}

export function RepositoryBrowser() {
  const [assets, setAssets] = useState<RepoAsset[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState("")
  const { toast } = useToast()
  const client = useApolloClient();
  const loadAssets = async () => {
    try {
      setLoading(true)
      const { data } = await client.query({
        query: LIST_REPOSITORY_ASSETS,
        variables: { limit: 50, jobId: null, include_download: true },
        fetchPolicy: "network-only",
      })
      setAssets(data.listRepositoryAssets)
    } catch (e) {
      console.error("Failed to load assets", e)
      toast({ title: "Error", description: "Failed to load repository assets", variant: "destructive" as any })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAssets()
  }, [])

  const filtered = assets.filter(a => a.filename.toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-foreground">Repository</h2>
        <div className="flex items-center gap-2">
          <Input placeholder="Search filename..." value={search} onChange={(e) => setSearch(e.target.value)} className="w-64" />
          <Button variant="ghost" onClick={loadAssets}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((asset) => (
            <Card key={asset.assetId} className="glass border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  {asset.mimeType.startsWith("image/") ? (
                    <ImageIcon className="h-4 w-4" />
                  ) : (
                    <FileText className="h-4 w-4" />
                  )}
                  {asset.filename}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground space-y-2">
                <div>Job: {asset.jobId || "-"}</div>
                <div>Size: {Math.round(asset.sizeBytes / 1024)} KB</div>
                <div>Created: {new Date(asset.createdAt).toLocaleString()}</div>
                {asset.downloadUrl && (
                  <Button asChild size="sm" variant="secondary" className="mt-1">
                    <a href={asset.downloadUrl} target="_blank" rel="noreferrer">
                      <Download className="h-3 w-3 mr-1" /> Download
                    </a>
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}


