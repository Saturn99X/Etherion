"use client"

import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Mic, Square } from 'lucide-react'

interface Props {
  onText: (text: string) => void
  className?: string
}

export function AudioRecordButton({ onText, className }: Props) {
  const [recording, setRecording] = useState(false)
  const [supported, setSupported] = useState<{ stt: boolean; media: boolean }>({ stt: false, media: false })
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  // Use any to avoid TS DOM lib requirements; this is browser-only
  const recognitionRef = useRef<any>(null)

  useEffect(() => {
    const sttOk = typeof window !== 'undefined' && (('SpeechRecognition' in window) || ('webkitSpeechRecognition' in window as any))
    const mediaOk = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
    setSupported({ stt: !!sttOk, media: mediaOk })
  }, [])

  const startSTT = async () => {
    try {
      const Rec: any = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (!Rec) return await startMediaRecorder()
      const rec: any = new Rec()
      recognitionRef.current = rec
      rec.lang = (navigator as any).language || 'en-US'
      rec.interimResults = true
      let finalText = ''
      rec.onresult = (event: any) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i]
          if (res.isFinal) finalText += res[0].transcript + ' '
        }
      }
      rec.onerror = () => { setRecording(false) }
      rec.onend = () => {
        setRecording(false)
        if (finalText.trim()) onText(finalText.trim())
      }
      rec.start()
      setRecording(true)
    } catch (e) {
      console.warn('SpeechRecognition failed; falling back to MediaRecorder', e)
      await startMediaRecorder()
    }
  }

  const startMediaRecorder = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      mediaRecorderRef.current = mr
      chunksRef.current = []
      mr.ondataavailable = (e) => e.data && chunksRef.current.push(e.data)
      mr.onstop = () => {
        setRecording(false)
        // No network in Step 5 — do not send audio anywhere.
        // Provide a small hint text so user sees something inserted.
        onText('[voice captured]')
      }
      mr.start()
      setRecording(true)
    } catch (e) {
      console.error('Microphone permission denied or unsupported', e)
      setRecording(false)
    }
  }

  const stopAll = () => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop() } catch {}
      recognitionRef.current = null
    }
    if (mediaRecorderRef.current) {
      try {
        if (mediaRecorderRef.current.state !== 'inactive') mediaRecorderRef.current.stop()
        mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop())
      } catch {}
      mediaRecorderRef.current = null
    }
    setRecording(false)
  }

  const onToggle = async () => {
    if (recording) return stopAll()
    if (supported.stt) return startSTT()
    if (supported.media) return startMediaRecorder()
    console.warn('No STT/MediaRecorder available in this browser')
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={onToggle}
      className={`h-8 w-auto px-2 glass-button text-xs ${className || ''}`}
      title={recording ? 'Stop' : 'Record'}
    >
      {recording ? <Square className="h-3 w-3 mr-2 text-red-400" /> : <Mic className="h-3 w-3 mr-2" />}
      {recording ? 'Recording…' : 'Mic'}
    </Button>
  )
}
