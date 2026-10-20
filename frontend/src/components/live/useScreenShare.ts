import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import {
  downsampleToGrayscale,
  isScreenChanged,
  SCREEN_THUMB_HEIGHT,
  SCREEN_THUMB_WIDTH,
} from '../../lib/screenFrames';
import { logger } from '../../lib/logger';

interface ScreenShareCallbacks {
  previewVideoRef: RefObject<HTMLVideoElement | null>;
  onFrame: (base64: string) => void;
  onStopped: () => void;
}

export function useScreenShare({ previewVideoRef, onFrame, onStopped }: ScreenShareCallbacks) {
  const [isSharing, setIsSharing] = useState(false);
  const [shareProblem, setShareProblem] = useState<string | null>(null);
  const screenVideoRef = useRef<HTMLVideoElement | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const screenCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const screenThumbRef = useRef<HTMLCanvasElement | null>(null);
  const screenIntervalRef = useRef<number | null>(null);
  const lastSentThumbRef = useRef<number[] | null>(null);
  const callbacksRef = useRef({ previewVideoRef, onFrame, onStopped });

  useEffect(() => {
    callbacksRef.current = { previewVideoRef, onFrame, onStopped };
  }, [previewVideoRef, onFrame, onStopped]);

  const shareSupported =
    typeof navigator !== 'undefined' && typeof navigator.mediaDevices?.getDisplayMedia === 'function';

  const sendFullFrame = useCallback(() => {
    const video = screenVideoRef.current;
    if (!video || video.videoWidth === 0) return;
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
    callbacksRef.current.onFrame(base64Data);
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

  const stop = useCallback((announceStop: boolean) => {
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
      if (was && announceStop) callbacksRef.current.onStopped();
      return false;
    });
  }, []);

  const toggle = useCallback(async () => {
    if (screenStreamRef.current) {
      stop(true);
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
      const preview = callbacksRef.current.previewVideoRef.current;
      if (preview) preview.srcObject = stream;
      stream.getVideoTracks()[0]?.addEventListener('ended', () => stop(true));
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
      sendFullFrame();
      if (screenIntervalRef.current !== null) window.clearInterval(screenIntervalRef.current);
      screenIntervalRef.current = window.setInterval(() => {
        const thumb = captureThumb();
        if (!thumb) return;
        if (isScreenChanged(lastSentThumbRef.current, thumb)) {
          lastSentThumbRef.current = thumb;
          sendFullFrame();
        }
      }, 1000);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'NotAllowedError') return;
      logger.error('Error accessing screen share', err);
      setShareProblem("Screen sharing didn't start. Try again.");
    }
  }, [captureThumb, sendFullFrame, stop]);

  useEffect(() => () => {
    if (screenIntervalRef.current !== null) window.clearInterval(screenIntervalRef.current);
    if (screenStreamRef.current) screenStreamRef.current.getTracks().forEach((t) => t.stop());
  }, []);

  return { isSharing, shareProblem, shareSupported, toggleShare: toggle, stopShare: stop };
}
