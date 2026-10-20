import { phaseMinutes, type InterviewTrackOption } from '../../lib/interviewOptions';

interface TrackCardProps {
  track: InterviewTrackOption;
  selected: boolean;
  durationMinutes: number;
  onSelect: () => void;
  isDarkMode: boolean;
}

export function TrackCard({ track, selected, durationMinutes, onSelect, isDarkMode }: TrackCardProps) {
  return (
    <label className={`track-card ${isDarkMode ? 'track-card--dark' : 'track-card--light'}${selected ? ' track-card--selected' : ''}`}>
      <input
        type="radio"
        name="interview-track"
        className="track-card__input"
        checked={selected}
        onChange={onSelect}
        aria-label={track.title}
      />
      <span className="track-card__title">{track.title}</span>
      <ol className="track-card__phases">
        {track.phases.map((phase, index) => (
          <li key={phase.key} className="track-card__phase">
            <span className="track-card__phase-index">{index + 1}</span>
            <span className="track-card__phase-title">{phase.title}</span>
            <span className="track-card__phase-minutes">~{phaseMinutes(phase.share, durationMinutes)} min</span>
          </li>
        ))}
      </ol>
    </label>
  );
}
