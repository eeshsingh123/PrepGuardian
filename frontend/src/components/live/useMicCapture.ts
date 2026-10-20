import { useCallback, useEffect, useRef, useState } from 'react';
import { logger } from '../../lib/logger';

export type MicProblem = 'denied' | 'not-found';

interface MicCaptureCallbacks {
  onFrame: (base64: string) => void;
  onStarted: () => void;
  onMutedChange: (muted: boolean) => void;
  onTrackEnded: () => void;
}

export function useMicCapture({ onFrame, onStarted, onMutedChange, onTrackEnded }: MicCaptureCallbacks) {
  const [muted, setMuted] = useState(false);
  const [micProblem, setMicProblem] = useState<MicProblem | null>(null);
  const micContextRef = useRef<AudioContext | null>(null);
  const micProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const mutedRef = useRef(false);
  const callbacksRef = useRef({ onFrame, onStarted, onMutedChange, onTrackEnded });

  useEffect(() => {
    callbacksRef.current = { onFrame, onStarted, onMutedChange, onTrackEnded };
  }, [onFrame, onStarted, onMutedChange, onTrackEnded]);

  const stop = useCallback(() => {
    if (micProcessorRef.current) {
      micProcessorRef.current.disconnect();
      micProcessorRef.current = null;
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    if (micContextRef.current) {
      void micContextRef.current.close().catch(() => undefined);
      micContextRef.current = null;
    }
    mutedRef.current = false;
    setMuted(false);
  }, []);

  const hasStream = useCallback(() => micStreamRef.current !== null, []);

  const clearMicProblem = useCallback(() => setMicProblem(null), []);

  const start = useCallback(async (): Promise<boolean> => {
    setMicProblem(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;
      const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const context = new Ctor({ sampleRate: 16000 });
      micContextRef.current = context;
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (e) => {
        if (mutedRef.current) return;
        const channelData = e.inputBuffer.getChannelData(0);
        const pcmData = new Int16Array(channelData.length);
        for (let i = 0; i < channelData.length; i++) {
          const s = Math.max(-1, Math.min(1, channelData[i]));
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        const buf = new ArrayBuffer(pcmData.length * 2);
        new Int16Array(buf).set(pcmData);
        const bytes = new Uint8Array(buf);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        callbacksRef.current.onFrame(window.btoa(binary));
      };
      source.connect(processor);
      processor.connect(context.destination);
      micProcessorRef.current = processor;
      stream.getAudioTracks()[0]?.addEventListener('ended', () => {
        micStreamRef.current = null;
        callbacksRef.current.onTrackEnded();
      });
      callbacksRef.current.onStarted();
      return true;
    } catch (err) {
      const name = err instanceof DOMException ? err.name : '';
      setMicProblem(name === 'NotAllowedError' ? 'denied' : 'not-found');
      logger.error('Error accessing microphone', err);
      return false;
    }
  }, []);

  const toggleMute = useCallback(() => {
    if (mutedRef.current) {
      mutedRef.current = false;
      setMuted(false);
      callbacksRef.current.onMutedChange(false);
      if (!micStreamRef.current) {
        void start().then((ok) => {
          if (!ok) {
            mutedRef.current = true;
            setMuted(true);
            callbacksRef.current.onMutedChange(true);
          }
        });
      }
    } else {
      mutedRef.current = true;
      setMuted(true);
      callbacksRef.current.onMutedChange(true);
    }
  }, [start]);

  useEffect(() => () => {
    if (micProcessorRef.current) micProcessorRef.current.disconnect();
    if (micStreamRef.current) micStreamRef.current.getTracks().forEach((t) => t.stop());
    if (micContextRef.current) void micContextRef.current.close().catch(() => undefined);
  }, []);

  return { muted, micProblem, hasStream, clearMicProblem, startMic: start, stopMic: stop, toggleMute };
}
