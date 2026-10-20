import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getInterviewOptions, createLiveSession, ApiError } from '../../lib/api';
import {
  loadInterviewChoice,
  phaseWindows,
  resolveChoice,
  saveInterviewChoice,
  type InterviewChoice,
  type InterviewOptions,
  type InterviewTrackOption,
} from '../../lib/interviewOptions';
import { logger } from '../../lib/logger';
import { useAnnouncer } from './useAnnouncer';
import { useAudioPlayback } from './useAudioPlayback';
import { useMicCapture } from './useMicCapture';
import { useScreenShare } from './useScreenShare';
import { useSessionClock, type SessionClockFrame } from './useSessionClock';
import { useLiveShortcuts } from './useLiveShortcuts';

export type LivePhase = 'setup' | 'connecting' | 'live' | 'ending';
export type AgentVoiceState = 'idle' | 'listening' | 'agent_speaking';
export type SessionEndReason = 'user_ended' | 'timer_expired';

export interface SessionBanner {
  kind: 'mic' | 'connection' | 'fatal';
  message: string;
  showRetry: boolean;
  showSetup: boolean;
  showTranscripts: boolean;
}

interface ServerMessage {
  error?: string;
  interrupted?: boolean;
  mime_type?: string;
  is_transcript?: boolean;
  partial?: boolean;
  data?: string;
  turn_complete?: boolean;
  session_clock?: SessionClockFrame;
  session_ended?: { reason?: string };
}

const CONNECT_TIMEOUT_MS = 15_000;

function wsBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (configured && configured.length > 0) {
    return configured.replace(/^http/, 'ws');
  }
  return 'ws://127.0.0.1:8000';
}

export function useLiveSession({
  onSessionEnded,
  previewVideoRef,
}: {
  onSessionEnded?: () => void;
  previewVideoRef: RefObject<HTMLVideoElement | null>;
}) {
  const navigate = useNavigate();

  const [phase, setPhase] = useState<LivePhase>('setup');
  const [choice, setChoiceState] = useState<InterviewChoice | null>(() => loadInterviewChoice());
  const [checkingMic, setCheckingMic] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [setupNotice, setSetupNotice] = useState<string | null>(null);
  const [agentVoice, setAgentVoice] = useState<AgentVoiceState>('idle');
  const [joined, setJoined] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [banner, setBanner] = useState<SessionBanner | null>(null);
  const [showEndModal, setShowEndModal] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const phaseRef = useRef<LivePhase>('setup');
  const clockReceivedRef = useRef(false);
  const endedRef = useRef(false);
  const expectedCloseRef = useRef(false);
  const connectTimeoutRef = useRef<number | null>(null);
  const speakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const turnBoundaryRef = useRef(false);
  const onSessionEndedRef = useRef(onSessionEnded);

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

  const { announcement, announce } = useAnnouncer();
  const playback = useAudioPlayback();

  const sendAudioFrame = useCallback((base64: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ mime_type: 'audio/pcm;rate=16000', data: base64 }));
  }, []);

  const sendScreenFrame = useCallback((base64: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ mime_type: 'image/jpeg', data: base64 }));
  }, []);

  const mic = useMicCapture({
    onFrame: sendAudioFrame,
    onStarted: () => setAgentVoice('listening'),
    onMutedChange: (isMuted) => {
      setAgentVoice(isMuted ? 'idle' : 'listening');
      if (!isMuted) setBanner((current) => (current?.kind === 'mic' ? null : current));
    },
    onTrackEnded: () =>
      setBanner((current) => {
        if (current && current.kind !== 'mic') return current;
        return {
          kind: 'mic',
          message: 'Your microphone disconnected. Reconnect it, then press M to unmute.',
          showRetry: false,
          showSetup: false,
          showTranscripts: false,
        };
      }),
  });

  const screen = useScreenShare({
    previewVideoRef,
    onFrame: sendScreenFrame,
    onStopped: () => announce('Screen sharing stopped.'),
  });

  const { muted: micMuted, stopMic, startMic, hasStream, clearMicProblem, toggleMute: toggleMicMute } = mic;
  const { stopShare, toggleShare: toggleScreenShare } = screen;
  const { playChunk, stopPlayback, toggleSpeaker } = playback;

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
      stopShare(false);
      stopPlayback();
      setShowEndModal(false);
      phaseRef.current = 'ending';
      setPhase('ending');
      onSessionEndedRef.current?.();
    },
    [closeSocket, stopMic, stopShare, stopPlayback],
  );
  const doEndRef = useRef(doEnd);
  useEffect(() => {
    doEndRef.current = doEnd;
  }, [doEnd]);

  const goLive = useCallback(() => {
    phaseRef.current = 'live';
    setPhase('live');
  }, []);

  const sessionClock = useSessionClock({
    ticking: phase === 'live' || phase === 'connecting',
    countingDown: phase === 'live',
    announce,
    onFirstFrame: goLive,
    onExpired: () => doEndRef.current('timer_expired'),
  });
  const { receiveFrame, resetClock } = sessionClock;

  const goToTranscripts = useCallback(() => {
    closeSocket();
    stopMic();
    stopShare(false);
    stopPlayback();
    navigate('/transcripts');
  }, [closeSocket, stopMic, navigate, stopPlayback, stopShare]);

  const markSpeaking = useCallback(() => {
    setAgentVoice('agent_speaking');
    if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
    speakingTimeoutRef.current = setTimeout(() => {
      setAgentVoice(micMuted ? 'idle' : 'listening');
    }, 600);
  }, [micMuted]);

  const handleServerMessage = useCallback(
    (msg: ServerMessage) => {
      if (msg.session_ended) {
        goToTranscripts();
        return;
      }
      if (msg.error !== undefined) {
        logger.error('Agent error:', msg.error);
        closeSocket();
        stopMic();
        stopShare(false);
        stopPlayback();
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
        clockReceivedRef.current = true;
        receiveFrame(msg.session_clock, phaseRef.current === 'live');
        clearConnectTimeout();
        return;
      }
      if (msg.interrupted) {
        stopPlayback();
        if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
        setAgentVoice(micMuted ? 'idle' : 'listening');
        return;
      }
      if (msg.mime_type === 'text/plain' && msg.is_transcript) {
        const text = msg.data ?? '';
        if (msg.partial) {
          if (turnBoundaryRef.current) {
            turnBoundaryRef.current = false;
            setTranscript(text);
          } else {
            setTranscript((prev) => prev + text);
          }
        } else {
          turnBoundaryRef.current = true;
          setTranscript(text);
        }
        return;
      }
      if (msg.mime_type === 'audio/pcm') {
        setJoined(true);
        playChunk(msg.data ?? '');
        markSpeaking();
        return;
      }
      if (msg.turn_complete) {
        if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
        speakingTimeoutRef.current = setTimeout(() => {
          setAgentVoice(micMuted ? 'idle' : 'listening');
        }, 300);
      }
    },
    [clearConnectTimeout, closeSocket, goToTranscripts, markSpeaking, micMuted, stopMic, playChunk, stopPlayback, stopShare, receiveFrame],
  );
  const handleServerMessageRef = useRef(handleServerMessage);
  useEffect(() => {
    handleServerMessageRef.current = handleServerMessage;
  }, [handleServerMessage]);

  const openSocket = useCallback(
    (ticket: string) => {
      expectedCloseRef.current = false;
      endedRef.current = false;
      const ws = new WebSocket(`${wsBaseUrl()}/agents/ws?ticket=${encodeURIComponent(ticket)}`);
      wsRef.current = ws;
      phaseRef.current = 'connecting';
      setPhase('connecting');
      setBanner(null);
      resetClock();
      clockReceivedRef.current = false;
      setJoined(false);
      turnBoundaryRef.current = false;
      clearConnectTimeout();
      connectTimeoutRef.current = window.setTimeout(() => {
        if (phaseRef.current === 'connecting' && !clockReceivedRef.current) {
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
        if (event.code === 1000) return;
        if (!clockReceivedRef.current && event.code === 1008) {
          closeSocket();
          stopMic();
          stopShare(false);
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
          stopShare(false);
          stopPlayback();
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
    [clearConnectTimeout, closeSocket, stopMic, stopPlayback, stopShare, resetClock],
  );

  const setChoice = useCallback((next: InterviewChoice) => {
    setChoiceState(next);
    saveInterviewChoice(next);
  }, []);

  const start = useCallback(async () => {
    if (!resolvedChoice) return;
    setSetupNotice(null);
    clearMicProblem();
    if (!hasStream()) {
      setCheckingMic(true);
      const ok = await startMic();
      setCheckingMic(false);
      if (!ok) return;
    } else {
      setBanner((current) => (current?.kind === 'mic' ? null : current));
    }
    setCreatingSession(true);
    let ticket: string;
    try {
      const session = await createLiveSession({
        interview_type: resolvedChoice.trackType,
        duration_minutes: resolvedChoice.durationMinutes,
      });
      ticket = session.ticket;
    } catch (err) {
      setCreatingSession(false);
      if (err instanceof ApiError && err.status === 422) {
        setSetupNotice("That setup isn't valid anymore. Please choose again.");
        return;
      }
      if (err instanceof ApiError && err.status === 409 && err.detail.includes('active_session')) {
        setSetupNotice('You already have an interview running in another tab. End it there, then try again.');
        return;
      }
      logger.error('Error creating live session', err);
      setBanner({
        kind: 'connection',
        message: "We couldn't reach the interview. Check your connection and try again.",
        showRetry: true,
        showSetup: true,
        showTranscripts: false,
      });
      return;
    }
    setCreatingSession(false);
    openSocket(ticket);
  }, [clearMicProblem, hasStream, openSocket, resolvedChoice, startMic]);

  const retry = useCallback(() => {
    void start();
  }, [start]);

  const cancelConnecting = useCallback(() => {
    closeSocket();
    stopMic();
    stopShare(false);
    phaseRef.current = 'setup';
    setPhase('setup');
  }, [closeSocket, stopMic, stopShare]);

  const backToSetup = useCallback(() => {
    closeSocket();
    stopMic();
    stopShare(false);
    stopPlayback();
    setBanner(null);
    phaseRef.current = 'setup';
    setPhase('setup');
  }, [closeSocket, stopMic, stopPlayback, stopShare]);

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
    toggleMicMute();
  }, [toggleMicMute]);

  const toggleShare = useCallback(() => {
    if (phaseRef.current !== 'live') return;
    void toggleScreenShare();
  }, [toggleScreenShare]);

  useLiveShortcuts({
    enabled: phase === 'live' && !showEndModal,
    onMute: toggleMute,
    onShare: toggleShare,
    onEnd: requestEnd,
  });

  useEffect(() => {
    if (phase !== 'live' && phase !== 'connecting') return;
    const handler = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [phase]);

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
      if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
    },
    [clearConnectTimeout],
  );

  const windows = selectedTrack && sessionClock.clock
    ? phaseWindows(selectedTrack.phases, sessionClock.clock.duration_seconds)
    : [];
  const currentWindow = windows[sessionClock.clock?.phase_index ?? -1] ?? null;
  const currentFill = currentWindow
    ? Math.min(1, Math.max(0, (sessionClock.elapsedSeconds - currentWindow.startSeconds) / Math.max(1, currentWindow.endSeconds - currentWindow.startSeconds)))
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
    creatingSession,
    micProblem: mic.micProblem,
    setupNotice,
    clock: sessionClock.clock,
    remainingSeconds: sessionClock.remainingSeconds,
    elapsedSeconds: sessionClock.elapsedSeconds,
    timeUp: sessionClock.timeUp,
    currentFill,
    agentVoice,
    joined,
    muted: micMuted,
    speakerMuted: playback.speakerMuted,
    isSharing: screen.isSharing,
    shareSupported: screen.shareSupported,
    shareProblem: screen.shareProblem,
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
