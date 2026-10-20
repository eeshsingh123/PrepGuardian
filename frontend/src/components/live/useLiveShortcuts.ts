import { useEffect } from 'react';

interface LiveShortcutCallbacks {
  enabled: boolean;
  onMute: () => void;
  onShare: () => void;
  onEnd: () => void;
}

export function useLiveShortcuts({ enabled, onMute, onShare, onEnd }: LiveShortcutCallbacks) {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable)) {
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const key = e.key.toLowerCase();
      if (key === 'm') onMute();
      else if (key === 's') onShare();
      else if (key === 'e') onEnd();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [enabled, onMute, onShare, onEnd]);
}
