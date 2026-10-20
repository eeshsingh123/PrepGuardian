import { useCallback, useEffect, useRef, useState } from 'react';

function createOutputContext(): AudioContext {
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  return new Ctor({ sampleRate: 24000 });
}

export function useAudioPlayback() {
  const [speakerMuted, setSpeakerMuted] = useState(false);
  const speakerMutedRef = useRef(false);
  const outputContextRef = useRef<AudioContext | null>(null);
  const nextPlayTimeRef = useRef(0);

  const playChunk = useCallback((base64Str: string) => {
    if (speakerMutedRef.current) return;
    if (!outputContextRef.current) {
      outputContextRef.current = createOutputContext();
      nextPlayTimeRef.current = outputContextRef.current.currentTime;
    }
    const ctx = outputContextRef.current;
    const raw = window.atob(base64Str);
    const pcm = new Int16Array(raw.length / 2);
    for (let i = 0; i < pcm.length; i++) {
      const low = raw.charCodeAt(i * 2);
      const high = raw.charCodeAt(i * 2 + 1);
      let val = (high << 8) | low;
      if (val > 32767) val -= 65536;
      pcm[i] = val;
    }
    const float32 = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) {
      float32[i] = pcm[i] / 32768.0;
    }
    const buffer = ctx.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const startTime = Math.max(nextPlayTimeRef.current, ctx.currentTime);
    source.start(startTime);
    nextPlayTimeRef.current = startTime + buffer.duration;
  }, []);

  const stop = useCallback(() => {
    if (outputContextRef.current) {
      void outputContextRef.current.close().catch(() => undefined);
      outputContextRef.current = null;
    }
    nextPlayTimeRef.current = 0;
  }, []);

  const toggleSpeaker = useCallback(() => {
    speakerMutedRef.current = !speakerMutedRef.current;
    setSpeakerMuted(speakerMutedRef.current);
  }, []);

  useEffect(() => () => {
    if (outputContextRef.current) {
      void outputContextRef.current.close().catch(() => undefined);
      outputContextRef.current = null;
    }
  }, []);

  return { speakerMuted, playChunk, stopPlayback: stop, toggleSpeaker };
}
