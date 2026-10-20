import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getInterviewOptions } from '../../lib/api';
import {
  loadInterviewChoice,
  phaseWindows,
  resolveChoice,
  saveInterviewChoice,
  type InterviewChoice,
  type InterviewOptions,
  type InterviewTrackOption,
} from '../../lib/interviewOptions';
import {
  downsampleToGrayscale,
  isScreenChanged,
  SCREEN_THUMB_HEIGHT,
  SCREEN_THUMB_WIDTH,
} from '../../lib/screenFrames';
import { logger } from '../../lib/logger';
import { useAuth } from '../../lib/auth';

export type LivePhase = 'setup' | 'connecting' | 'live' | 'ending';
export type AgentVoiceState = 'idle' | 'listening' | 'agent_speaking';
export type MicProblem = 'denied' | 'not-found';
export type SessionEndReason = 'user_ended' | 'timer_expired';

export interface SessionClockFrame {
  started_at: string;
  elapsed_seconds: number;
  duration_seconds: number;
  phase_key: string;
  phase_title: string;
  phase_index: number;
  phase_count: number;
}

export interface SessionBanner {
  kind: 'mic' | 'connection' | 'fatal';
  message: string;
  showRetry: boolean;
  showSetup: boolean;
  showTranscripts: boolean;
}

interface ServerMessage {
  error?: unknown;
  interrupted?: boolean;
  mime_type?: string;
  is_transcript?: boolean;
  data?: string;
  turn_complete?: boolean;
  session_clock?: SessionClockFrame;
}

const CONNECT_TIMEOUT_MS = 15_000;
const GRACE_AFTER_ZERO_MS = 60_000;
const TEN_MINUTES_SECONDS = 10 * 60;
const THREE_MINUTES_SECONDS = 3 * 60;
const ONE_MINUTE_SECONDS = 60;

function wsBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (configured && configured.length > 0) {
    return configured.replace(/^http/, 'ws');
  }
  return 'ws://127.0.0.1:8000';
}

function playBeep(outputContextRef: { current: AudioContext | null }) {
  try {
    if (!outputContextRef.current) {
      const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      outputContextRef.current = new Ctor({ sampleRate: 24000 });
    }
    const ctx = outputContextRef.current;
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.4);
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start();
    oscillator.stop(ctx.currentTime + 0.45);
  } catch (e) {
    logger.error('Error playing timer beep', e);
  }
}

export function useLiveSession({
  onSessionEnded,
  previewVideoRef,
}: {
  onSessionEnded?: () => void;
  previewVideoRef: RefObject<HTMLVideoElement | null>;
}) {
  const { accessToken } = useAuth();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<LivePhase>('setup');
  const [choice, setChoiceState] = useState<InterviewChoice | null>(() => loadInterviewChoice());
  const [checkingMic, setCheckingMic] = useState(false);
  const [micProblem, setMicProblem] = useState<MicProblem | null>(null);
  const [setupNotice, setSetupNotice] = useState<string | null>(null);
  const [clock, setClock] = useState<SessionClockFrame | null>(null);
  const [clockArrivedAt, setClockArrivedAt] = useState(0);
  const [nowMs, setNowMs] = useState(0);
  const [agentVoice, setAgentVoice] = useState<AgentVoiceState>('idle');
  const [muted, setMuted] = useState(false);
  const [speakerMuted, setSpeakerMuted] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [shareProblem, setShareProblem] = useState<string | null>(null);
  const [transcript, setTranscript] = useState('');
  const [banner, setBanner] = useState<SessionBanner | null>(null);
  const [announcement, setAnnouncement] = useState<{ id: number; text: string } | null>(null);
  const [showEndModal, setShowEndModal] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const phaseRef = useRef<LivePhase>('setup');
  const clockRef = useRef<SessionClockFrame | null>(null);
  const mutedRef = useRef(false);
  const speakerMutedRef = useRef(false);
  const endedRef = useRef(false);
  const expectedCloseRef = useRef(false);
  const timeUpAtRef = useRef<number | null>(null);
  const announcedMarksRef = useRef<Set<string>>(new Set());
  const connectTimeoutRef = useRef<number | null>(null);
  const lastPhaseIndexRef = useRef<number | null>(null);
  const announcementIdRef = useRef(0);
  const onSessionEndedRef = useRef(onSessionEnded);

  const micContextRef = useRef<AudioContext | null>(null);
  const micProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const outputContextRef = useRef<AudioContext | null>(null);
  const nextPlayTimeRef = useRef(0);
  const speakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const screenVideoRef = useRef<HTMLVideoElement | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const screenCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const screenThumbRef = useRef<HTMLCanvasElement | null>(null);
  const screenIntervalRef = useRef<number | null>(null);
  const lastSentThumbRef = useRef<number[] | null>(null);

  useEffect(() => {
    onSessionEndedRef.current = onSessionEnded;
  }, [onSessionEnded]);

  const optionsQuery = useQuery({
    queryKey: ['interview-options'],
    queryFn: getInterviewOptions,
  });
  const options: InterviewOptions | undefined = optionsQuery.data;
  const resolvedChoice = options ? resolveChoice(options, choice) : null;
  const selectedTrack: InterviewTrackOption | null =
    options && resolvedChoice ? options.tracks.find((t) => t.type === resolvedChoice.trackType) ?? null : null;
  const interviewerName = options?.interviewer_name ?? '';

  const announce = useCallback((text: string) => {
    announcementIdRef.current += 1;
    setAnnouncement({ id: announcementIdRef.current, text });
  }, []);

  const setChoice = useCallback((next: InterviewChoice) => {
    setChoiceState(next);
    saveInterviewChoice(next);
  }, []);

  const elapsedSeconds = clock
    ? Math.min(clock.duration_seconds, Math.max(0, clock.elapsed_seconds + (nowMs - clockArrivedAt) / 1000))
    : 0;
  const remainingSeconds = clock ? Math.max(0, clock.duration_seconds - elapsedSeconds) : 0;
  const timeUp = clock !== null && remainingSeconds <= 0;

  const stopMic = useCallback(() => {
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
    setMuted(false);
    mutedRef.current = false;
  }, []);

  const stopScreenShare = useCallback(
    (announceStop: boolean) => {
      if (screenIntervalRef.current !== null) {
        window.clearInterval(screenIntervalRef.current);
        screenIntervalRef.current = null;
      }
      if (screenStreamRef.current) {
        screenStreamRef.current.getTracks().forEach((t) => t.stop());
        screenStreamRef.current = null;
      }
      lastSentThumbRef.current = null;
      setIsSharing((was) => {
        if (was && announceStop) announce('Screen sharing stopped.');
        return false;
      });
    },
    [announce],
  );

  const stopAudioPlayback = useCallback(() => {
    if (outputContextRef.current) {
      void outputContextRef.current.close().catch(() => undefined);
      outputContextRef.current = null;
    }
    nextPlayTimeRef.current = 0;
  }, []);

  const clearConnectTimeout = useCallback(() => {
    if (connectTimeoutRef.current !== null) {
      window.clearTimeout(connectTimeoutRef.current);
      connectTimeoutRef.current = null;
    }
  }, []);

  const closeSocket = useCallback(() => {
    expectedCloseRef.current = true;
    clearConnectTimeout();
    if (wsRef.current && (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN)) {
      wsRef.current.close();
    }
    wsRef.current = null;
  }, [clearConnectTimeout]);

  const doEnd = useCallback(
    (reason: SessionEndReason) => {
      if (endedRef.current) return;
      endedRef.current = true;
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({ mime_type: 'application/session-control', event: 'session_ended', reason }),
        );
      }
      closeSocket();
      stopMic();
      stopScreenShare(false);
      stopAudioPlayback();
      setShowEndModal(false);
      phaseRef.current = 'ending';
      setPhase('ending');
      onSessionEndedRef.current?.();
    },
    [closeSocket, stopAudioPlayback, stopMic, stopScreenShare],
  );
  const doEndRef = useRef(doEnd);
  useEffect(() => {
    doEndRef.current = doEnd;
  }, [doEnd]);

  const playAudioChunk = useCallback((base64Str: string) => {
    if (!outputContextRef.current) {
      const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      outputContextRef.current = new Ctor({ sampleRate: 24000 });
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

  const markSpeaking = useCallback(() => {
    setAgentVoice('agent_speaking');
    if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
    speakingTimeoutRef.current = setTimeout(() => {
      setAgentVoice(mutedRef.current ? 'idle' : 'listening');
    }, 600);
  }, []);

  const handleServerMessage = useCallback(
    (msg: ServerMessage) => {
      if (msg.error !== undefined) {
        logger.error('Agent error:', msg.error);
        expectedCloseRef.current = true;
        closeSocket();
        stopMic();
        stopScreenShare(false);
        stopAudioPlayback();
        setBanner({
          kind: 'fatal',
          message: 'The interview hit a problem and had to stop. Everything up to now is saved.',
          showRetry: false,
          showSetup: true,
          showTranscripts: true,
        });
        return;
      }
      if (msg.session_clock) {
        const frame = msg.session_clock;
        clockRef.current = frame;
        setClockArrivedAt(performance.now());
        setClock(frame);
        clearConnectTimeout();
        if (lastPhaseIndexRef.current !== frame.phase_index) {
          lastPhaseIndexRef.current = frame.phase_index;
          if (phaseRef.current === 'live') {
            announce(`Now in phase ${frame.phase_index + 1} of ${frame.phase_count}: ${frame.phase_title}.`);
          }
        }
        if (phaseRef.current === 'connecting') {
          phaseRef.current = 'live';
          setPhase('live');
        }
        return;
      }
      if (msg.interrupted) {
        stopAudioPlayback();
        if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
        setAgentVoice(mutedRef.current ? 'idle' : 'listening');
        return;
      }
      if (msg.mime_type === 'text/plain' && msg.is_transcript) {
        setTranscript(msg.data ?? '');
        return;
      }
      if (msg.mime_type === 'audio/pcm') {
        if (!speakerMutedRef.current) playAudioChunk(msg.data ?? '');
        markSpeaking();
        return;
      }
      if (msg.turn_complete) {
        if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
        speakingTimeoutRef.current = setTimeout(() => {
          setAgentVoice(mutedRef.current ? 'idle' : 'listening');
        }, 300);
      }
    },
    [announce, clearConnectTimeout, closeSocket, markSpeaking, playAudioChunk, stopAudioPlayback, stopMic, stopScreenShare],
  );
  const handleServerMessageRef = useRef(handleServerMessage);
  useEffect(() => {
    handleServerMessageRef.current = handleServerMessage;
  }, [handleServerMessage]);

  const openSocket = useCallback(
    (sessionChoice: InterviewChoice) => {
      if (!accessToken) return;
      expectedCloseRef.current = false;
      endedRef.current = false;
      const sessionId = `sess_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
      const wsUrl =
        `${wsBaseUrl()}/agents/ws/${sessionId}` +
        `?token=${encodeURIComponent(accessToken)}` +
        `&interview_type=${encodeURIComponent(sessionChoice.trackType)}` +
        `&duration_minutes=${sessionChoice.durationMinutes}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      phaseRef.current = 'connecting';
      setPhase('connecting');
      setBanner(null);
      setClock(null);
      clockRef.current = null;
      lastPhaseIndexRef.current = null;
      timeUpAtRef.current = null;
      announcedMarksRef.current = new Set();
      clearConnectTimeout();
      connectTimeoutRef.current = window.setTimeout(() => {
        if (phaseRef.current === 'connecting' && clockRef.current === null) {
          setBanner({
            kind: 'connection',
            message: "We couldn't reach the interview. Check your connection and try again.",
            showRetry: true,
            showSetup: true,
            showTranscripts: false,
          });
        }
      }, CONNECT_TIMEOUT_MS);

      ws.onmessage = (event) => {
        try {
          handleServerMessageRef.current(JSON.parse(event.data as string) as ServerMessage);
        } catch (e) {
          logger.error('Error parsing websocket message', e);
        }
      };
      ws.onclose = (event) => {
        clearConnectTimeout();
        if (expectedCloseRef.current || endedRef.current) return;
        if (clockRef.current === null && event.code === 1008) {
          closeSocket();
          stopMic();
          stopScreenShare(false);
          phaseRef.current = 'setup';
          setPhase('setup');
          setSetupNotice("That setup isn't valid anymore. Please choose again.");
          return;
        }
        if (phaseRef.current === 'connecting') {
          setBanner({
            kind: 'connection',
            message: "We couldn't reach the interview. Check your connection and try again.",
            showRetry: true,
            showSetup: true,
            showTranscripts: false,
          });
          return;
        }
        if (phaseRef.current === 'live') {
          stopMic();
          stopScreenShare(false);
          stopAudioPlayback();
          setBanner({
            kind: 'connection',
            message: 'Connection lost. Everything up to now is saved.',
            showRetry: false,
            showSetup: false,
            showTranscripts: true,
          });
        }
      };
      ws.onerror = () => {
        logger.error('WebSocket error');
      };
    },
    [accessToken, clearConnectTimeout, closeSocket, stopAudioPlayback, stopMic, stopScreenShare],
  );

  const startMicCapture = useCallback(async (): Promise<boolean> => {
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
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
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
        wsRef.current.send(JSON.stringify({ mime_type: 'audio/pcm;rate=16000', data: window.btoa(binary) }));
      };
      source.connect(processor);
      processor.connect(context.destination);
      micProcessorRef.current = processor;
      stream.getAudioTracks()[0]?.addEventListener('ended', () => {
        micStreamRef.current = null;
        setBanner((current) => {
          if (current && current.kind !== 'mic') return current;
          return {
            kind: 'mic',
            message: 'Your microphone disconnected. Reconnect it, then press M to unmute.',
            showRetry: false,
            showSetup: false,
            showTranscripts: false,
          };
        });
      });
      setAgentVoice('listening');
      return true;
    } catch (err) {
      const name = err instanceof DOMException ? err.name : '';
      setMicProblem(name === 'NotAllowedError' ? 'denied' : 'not-found');
      logger.error('Error accessing microphone', err);
      return false;
    }
  }, []);

  const start = useCallback(async () => {
    if (!resolvedChoice || !accessToken) return;
    setSetupNotice(null);
    setMicProblem(null);
    if (!micStreamRef.current) {
      setCheckingMic(true);
      const ok = await startMicCapture();
      setCheckingMic(false);
      if (!ok) return;
    } else {
      setBanner((current) => (current?.kind === 'mic' ? null : current));
    }
    openSocket(resolvedChoice);
  }, [accessToken, openSocket, resolvedChoice, startMicCapture]);

  const retry = useCallback(() => {
    if (!resolvedChoice) return;
    if (!micStreamRef.current) {
      void start();
      return;
    }
    openSocket(resolvedChoice);
  }, [openSocket, resolvedChoice, start]);

  const cancelConnecting = useCallback(() => {
    closeSocket();
    stopMic();
    stopScreenShare(false);
    phaseRef.current = 'setup';
    setPhase('setup');
  }, [closeSocket, stopMic, stopScreenShare]);

  const backToSetup = useCallback(() => {
    closeSocket();
    stopMic();
    stopScreenShare(false);
    stopAudioPlayback();
    setBanner(null);
    phaseRef.current = 'setup';
    setPhase('setup');
  }, [closeSocket, stopAudioPlayback, stopMic, stopScreenShare]);

  const goToTranscripts = useCallback(() => {
    closeSocket();
    stopMic();
    stopScreenShare(false);
    stopAudioPlayback();
    navigate('/transcripts');
  }, [closeSocket, navigate, stopAudioPlayback, stopMic, stopScreenShare]);

  const requestEnd = useCallback(() => {
    if (phaseRef.current === 'connecting') {
      cancelConnecting();
      return;
    }
    if (phaseRef.current === 'live') setShowEndModal(true);
  }, [cancelConnecting]);

  const confirmEnd = useCallback(() => {
    doEnd('user_ended');
  }, [doEnd]);

  const toggleMute = useCallback(() => {
    if (phaseRef.current !== 'live') return;
    if (mutedRef.current) {
      mutedRef.current = false;
      setMuted(false);
      setAgentVoice('listening');
      setBanner((current) => (current?.kind === 'mic' ? null : current));
      if (!micStreamRef.current) {
        void startMicCapture().then((ok) => {
          if (!ok) {
            mutedRef.current = true;
            setMuted(true);
          }
        });
      }
    } else {
      mutedRef.current = true;
      setMuted(true);
      setAgentVoice('idle');
    }
  }, [startMicCapture]);

  const toggleSpeaker = useCallback(() => {
    speakerMutedRef.current = !speakerMutedRef.current;
    setSpeakerMuted(speakerMutedRef.current);
  }, []);

  const captureThumb = useCallback((): number[] | null => {
    const video = screenVideoRef.current;
    if (!video || video.videoWidth === 0) return null;
    if (!screenThumbRef.current) screenThumbRef.current = document.createElement('canvas');
    const thumb = screenThumbRef.current;
    thumb.width = SCREEN_THUMB_WIDTH;
    thumb.height = SCREEN_THUMB_HEIGHT;
    const ctx = thumb.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, SCREEN_THUMB_WIDTH, SCREEN_THUMB_HEIGHT);
    const image = ctx.getImageData(0, 0, SCREEN_THUMB_WIDTH, SCREEN_THUMB_HEIGHT);
    return downsampleToGrayscale(image.data, SCREEN_THUMB_WIDTH, SCREEN_THUMB_HEIGHT);
  }, []);

  const sendFullScreenFrame = useCallback(() => {
    const video = screenVideoRef.current;
    if (!video || video.videoWidth === 0) return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (!screenCanvasRef.current) screenCanvasRef.current = document.createElement('canvas');
    const canvas = screenCanvasRef.current;
    const maxWidth = 1024;
    const scale = Math.min(1, maxWidth / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const base64Data = canvas.toDataURL('image/jpeg', 0.6).split(',')[1];
    wsRef.current.send(JSON.stringify({ mime_type: 'image/jpeg', data: base64Data }));
  }, []);

  const stopShare = useCallback(() => {
    stopScreenShare(true);
  }, [stopScreenShare]);

  const toggleShare = useCallback(async () => {
    if (phaseRef.current !== 'live') return;
    if (screenStreamRef.current) {
      stopShare();
      return;
    }
    if (typeof navigator.mediaDevices?.getDisplayMedia !== 'function') return;
    setShareProblem(null);
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      screenStreamRef.current = stream;
      if (!screenVideoRef.current) screenVideoRef.current = document.createElement('video');
      screenVideoRef.current.muted = true;
      screenVideoRef.current.srcObject = stream;
      if (previewVideoRef.current) previewVideoRef.current.srcObject = stream;
      stream.getVideoTracks()[0]?.addEventListener('ended', () => stopScreenShare(true));
      await new Promise<void>((resolve) => {
        if (screenVideoRef.current) {
          screenVideoRef.current.onloadedmetadata = () => resolve();
          screenVideoRef.current.play().catch(() => undefined);
        } else {
          resolve();
        }
      });
      setIsSharing(true);
      lastSentThumbRef.current = captureThumb();
      sendFullScreenFrame();
      if (screenIntervalRef.current !== null) window.clearInterval(screenIntervalRef.current);
      screenIntervalRef.current = window.setInterval(() => {
        const thumb = captureThumb();
        if (!thumb) return;
        if (isScreenChanged(lastSentThumbRef.current, thumb)) {
          lastSentThumbRef.current = thumb;
          sendFullScreenFrame();
        }
      }, 1000);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'NotAllowedError') return;
      logger.error('Error accessing screen share', err);
      setShareProblem("Screen sharing didn't start. Try again.");
    }
  }, [captureThumb, previewVideoRef, sendFullScreenFrame, stopScreenShare, stopShare]);

  useEffect(() => {
    if ((phase !== 'live' && phase !== 'connecting') || !clock) return;
    const id = window.setInterval(() => setNowMs(performance.now()), 1000);
    return () => window.clearInterval(id);
  }, [phase, clock]);

  useEffect(() => {
    if (phase !== 'live' || !clock) return;
    if (remainingSeconds > 0) {
      const marks: Array<[number, string, boolean]> = [
        [TEN_MINUTES_SECONDS, '10 minutes left', true],
        [THREE_MINUTES_SECONDS, '3 minutes left', true],
        [ONE_MINUTE_SECONDS, '1 minute left', false],
      ];
      for (const [threshold, text, beep] of marks) {
        if (remainingSeconds <= threshold && !announcedMarksRef.current.has(text)) {
          announcedMarksRef.current.add(text);
          announce(text);
          if (beep) playBeep(outputContextRef);
        }
      }
      return;
    }
    if (!announcedMarksRef.current.has("Time's up.")) {
      announcedMarksRef.current.add("Time's up.");
      announce("Time's up.");
      timeUpAtRef.current = performance.now();
    } else if (timeUpAtRef.current !== null && performance.now() - timeUpAtRef.current >= GRACE_AFTER_ZERO_MS) {
      doEndRef.current('timer_expired');
    }
  }, [announce, clock, phase, remainingSeconds]);

  useEffect(() => {
    if (phase !== 'live' && phase !== 'connecting') return;
    const handler = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [phase]);

  useEffect(() => {
    if (phase !== 'live' || showEndModal) return;
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable)) {
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const key = e.key.toLowerCase();
      if (key === 'm') toggleMute();
      else if (key === 's') void toggleShare();
      else if (key === 'e') requestEnd();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [phase, requestEnd, showEndModal, toggleMute, toggleShare]);

  useEffect(
    () => () => {
      expectedCloseRef.current = true;
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          // Socket already gone; nothing to clean up.
        }
        wsRef.current = null;
      }
      clearConnectTimeout();
      if (micProcessorRef.current) micProcessorRef.current.disconnect();
      if (micStreamRef.current) micStreamRef.current.getTracks().forEach((t) => t.stop());
      if (micContextRef.current) void micContextRef.current.close().catch(() => undefined);
      if (screenIntervalRef.current !== null) window.clearInterval(screenIntervalRef.current);
      if (screenStreamRef.current) screenStreamRef.current.getTracks().forEach((t) => t.stop());
      if (outputContextRef.current) void outputContextRef.current.close().catch(() => undefined);
      if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
    },
    [clearConnectTimeout],
  );

  const windows = selectedTrack && clock ? phaseWindows(selectedTrack.phases, clock.duration_seconds) : [];
  const currentWindow = windows[clock?.phase_index ?? -1] ?? null;
  const currentFill = currentWindow
    ? Math.min(1, Math.max(0, (elapsedSeconds - currentWindow.startSeconds) / Math.max(1, currentWindow.endSeconds - currentWindow.startSeconds)))
    : 0;

  return {
    phase,
    options,
    optionsLoading: optionsQuery.isPending,
    optionsError: optionsQuery.isError,
    reloadOptions: () => optionsQuery.refetch(),
    resolvedChoice,
    setChoice,
    selectedTrack,
    interviewerName,
    checkingMic,
    micProblem,
    setupNotice,
    clock,
    remainingSeconds,
    elapsedSeconds,
    timeUp,
    currentFill,
    agentVoice,
    muted,
    speakerMuted,
    isSharing,
    shareSupported: typeof navigator !== 'undefined' && typeof navigator.mediaDevices?.getDisplayMedia === 'function',
    shareProblem,
    transcript,
    banner,
    announcement,
    showEndModal,
    setShowEndModal,
    start,
    retry,
    cancelConnecting,
    backToSetup,
    goToTranscripts,
    requestEnd,
    confirmEnd,
    toggleMute,
    toggleSpeaker,
    toggleShare,
  };
}

export type UseLiveSession = ReturnType<typeof useLiveSession>;
