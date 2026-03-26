import { ToneOfVoiceLibrary } from "@/components/tone-of-voice-library"
import { AuthGuard } from "@/components/auth/auth-guard"

export default function ToneLibraryPage() {
  return (
    <AuthGuard>
      <ToneOfVoiceLibrary />
    </AuthGuard>
  )
}
