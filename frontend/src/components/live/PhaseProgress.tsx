import { phaseMinutes, type InterviewTrackOption } from '../../lib/interviewOptions';

interface PhaseProgressProps {
  track: InterviewTrackOption;
  durationMinutes: number;
  currentIndex: number;
  currentFill: number;
  ready: boolean;
  isDarkMode: boolean;
}

export function PhaseProgress({ track, durationMinutes, currentIndex, currentFill, ready, isDarkMode }: PhaseProgressProps) {
  const theme = isDarkMode ? 'phase-progress--dark' : 'phase-progress--light';
  const current = track.phases[currentIndex];
  const fullText = ready && current ? `Phase ${currentIndex + 1} of ${track.phases.length} — ${current.title}` : 'Getting ready…';
  const compactText = ready && current ? `${currentIndex + 1}/${track.phases.length} · ${current.title}` : 'Getting ready…';

  return (
    <div className={`phase-progress ${theme}`}>
      <p className="phase-progress__label">
        <span className="phase-progress__label-full">{fullText}</span>
        <span className="phase-progress__label-compact">{compactText}</span>
      </p>
      <div className="phase-progress__bar" aria-hidden="true">
        {track.phases.map((phase, index) => (
          <span
            key={phase.key}
            title={`${phase.title} · ~${phaseMinutes(phase.share, durationMinutes)} min`}
            style={{ flexGrow: phase.share }}
            className={`phase-progress__segment${
              index < currentIndex ? ' phase-progress__segment--done' : ''
            }${index === currentIndex && ready ? ' phase-progress__segment--current' : ''}`}
          >
            {index === currentIndex && ready && (
              <span
                className="phase-progress__fill"
                style={{ width: `${Math.round(currentFill * 100)}%` }}
              />
            )}
          </span>
        ))}
      </div>
    </div>
  );
}
