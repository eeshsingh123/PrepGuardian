export interface InterviewPhaseOption {
  key: string;
  title: string;
  share: number;
  goal: string;
}

export interface InterviewTrackOption {
  type: string;
  title: string;
  phases: InterviewPhaseOption[];
}

export interface InterviewOptions {
  interviewer_name: string;
  durations_minutes: number[];
  default_duration_minutes: number;
  tracks: InterviewTrackOption[];
}

export interface InterviewChoice {
  trackType: string;
  durationMinutes: number;
}

export interface PhaseWindow {
  key: string;
  title: string;
  startSeconds: number;
  endSeconds: number;
}

const CHOICE_STORAGE_KEY = 'prepguardian.interview.choice';

export function loadInterviewChoice(): InterviewChoice | null {
  try {
    const raw = window.localStorage.getItem(CHOICE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<InterviewChoice>;
    if (typeof parsed.trackType !== 'string' || typeof parsed.durationMinutes !== 'number') {
      return null;
    }
    return { trackType: parsed.trackType, durationMinutes: parsed.durationMinutes };
  } catch {
    return null;
  }
}

export function saveInterviewChoice(choice: InterviewChoice): void {
  try {
    window.localStorage.setItem(CHOICE_STORAGE_KEY, JSON.stringify(choice));
  } catch {
    // Storage may be unavailable; the in-memory choice still works for this visit.
  }
}

export function resolveChoice(options: InterviewOptions, stored: InterviewChoice | null): InterviewChoice {
  const track = options.tracks.find((t) => t.type === stored?.trackType) ?? options.tracks[0];
  const durationMinutes = options.durations_minutes.includes(stored?.durationMinutes ?? -1)
    ? (stored as InterviewChoice).durationMinutes
    : options.default_duration_minutes;
  return { trackType: track.type, durationMinutes };
}

export function phaseMinutes(share: number, durationMinutes: number): number {
  return Math.round(share * durationMinutes);
}

export function phaseWindows(phases: InterviewPhaseOption[], durationSeconds: number): PhaseWindow[] {
  let start = 0;
  return phases.map((phase) => {
    const end = start + phase.share * durationSeconds;
    const window = {
      key: phase.key,
      title: phase.title,
      startSeconds: Math.round(start),
      endSeconds: Math.round(end),
    };
    start = end;
    return window;
  });
}
