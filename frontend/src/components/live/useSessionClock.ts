import { useCallback, useEffect, useRef, useState } from 'react';

export interface SessionClockFrame {
  started_at: string;
  elapsed_seconds: number;
  duration_seconds: number;
  phase_key: string;
  phase_title: string;
  phase_index: number;
  phase_count: number;
}

interface SessionClockCallbacks {
  ticking: boolean;
  countingDown: boolean;
  announce: (text: string) => void;
  onFirstFrame: () => void;
  onExpired: () => void;
}

const GRACE_AFTER_ZERO_MS = 60_000;
const TEN_MINUTES_SECONDS = 10 * 60;
const THREE_MINUTES_SECONDS = 3 * 60;
const ONE_MINUTE_SECONDS = 60;

export function useSessionClock({ ticking, countingDown, announce, onFirstFrame, onExpired }: SessionClockCallbacks) {
  const [clock, setClock] = useState<SessionClockFrame | null>(null);
  const [arrivedAt, setArrivedAt] = useState(0);
  const [nowMs, setNowMs] = useState(0);
  const lastPhaseIndexRef = useRef<number | null>(null);
  const announcedMarksRef = useRef<Set<string>>(new Set());
  const graceTimeoutRef = useRef<number | null>(null);
  const expiredRef = useRef(onExpired);

  useEffect(() => {
    expiredRef.current = onExpired;
  }, [onExpired]);

  const resetClock = useCallback(() => {
    setClock(null);
    lastPhaseIndexRef.current = null;
    announcedMarksRef.current = new Set();
    if (graceTimeoutRef.current !== null) {
      window.clearTimeout(graceTimeoutRef.current);
      graceTimeoutRef.current = null;
    }
  }, []);

  const receiveFrame = useCallback(
    (frame: SessionClockFrame, isLiveNow: boolean) => {
      setClock(frame);
      setArrivedAt(performance.now());
      if (lastPhaseIndexRef.current !== frame.phase_index) {
        lastPhaseIndexRef.current = frame.phase_index;
        if (isLiveNow) {
          announce(`Now in phase ${frame.phase_index + 1} of ${frame.phase_count}: ${frame.phase_title}.`);
        }
      }
      if (!isLiveNow) {
        onFirstFrame();
      }
    },
    [announce, onFirstFrame],
  );

  useEffect(() => {
    if (!ticking || !clock) return;
    const id = window.setInterval(() => setNowMs(performance.now()), 1000);
    return () => window.clearInterval(id);
  }, [ticking, clock]);

  useEffect(() => () => {
    if (graceTimeoutRef.current !== null) {
      window.clearTimeout(graceTimeoutRef.current);
    }
  }, []);

  const elapsedSeconds = clock
    ? Math.min(clock.duration_seconds, Math.max(0, clock.elapsed_seconds + (nowMs - arrivedAt) / 1000))
    : 0;
  const remainingSeconds = clock ? Math.max(0, clock.duration_seconds - elapsedSeconds) : 0;
  const timeUp = clock !== null && remainingSeconds <= 0;

  useEffect(() => {
    if (!countingDown || !clock) return;
    if (remainingSeconds > 0) {
      for (const [threshold, text] of [
        [TEN_MINUTES_SECONDS, '10 minutes left'],
        [THREE_MINUTES_SECONDS, '3 minutes left'],
        [ONE_MINUTE_SECONDS, '1 minute left'],
      ] as const) {
        if (remainingSeconds <= threshold && !announcedMarksRef.current.has(text)) {
          announcedMarksRef.current.add(text);
          announce(text);
        }
      }
      return;
    }
    if (!announcedMarksRef.current.has("Time's up.")) {
      announcedMarksRef.current.add("Time's up.");
      announce("Time's up.");
      if (graceTimeoutRef.current !== null) {
        window.clearTimeout(graceTimeoutRef.current);
      }
      graceTimeoutRef.current = window.setTimeout(() => {
        expiredRef.current();
      }, GRACE_AFTER_ZERO_MS);
    }
  }, [announce, clock, countingDown, remainingSeconds]);

  return { clock, elapsedSeconds, remainingSeconds, timeUp, receiveFrame, resetClock };
}
