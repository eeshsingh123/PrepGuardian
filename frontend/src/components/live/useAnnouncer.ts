import { useCallback, useRef, useState } from 'react';

export interface Announcement {
  id: number;
  text: string;
}

export function useAnnouncer() {
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);
  const idRef = useRef(0);

  const announce = useCallback((text: string) => {
    idRef.current += 1;
    setAnnouncement({ id: idRef.current, text });
  }, []);

  return { announcement, announce };
}
