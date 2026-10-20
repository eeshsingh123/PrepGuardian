import type { InterviewOptions } from '../../lib/interviewOptions';
import { TrackCard } from './TrackCard';
import { DurationPicker } from './DurationPicker';
import type { MicProblem } from './useMicCapture';

interface SetupPanelProps {
  options: InterviewOptions | undefined;
  optionsLoading: boolean;
  optionsError: boolean;
  onRetryOptions: () => void;
  trackType: string;
  durationMinutes: number;
  onTrackTypeChange: (type: string) => void;
  onDurationChange: (minutes: number) => void;
  checkingMic: boolean;
  micProblem: MicProblem | null;
  setupNotice: string | null;
  onStart: () => void;
  isDarkMode: boolean;
}

export function SetupPanel({
  options,
  optionsLoading,
  optionsError,
  onRetryOptions,
  trackType,
  durationMinutes,
  onTrackTypeChange,
  onDurationChange,
  checkingMic,
  micProblem,
  setupNotice,
  onStart,
  isDarkMode,
}: SetupPanelProps) {
  const theme = isDarkMode ? 'live-setup--dark' : 'live-setup--light';
  const tracks = options?.tracks ?? [];
  const selectedTrack = tracks.find((t) => t.type === trackType) ?? tracks[0];
  const interviewerName = options?.interviewer_name ?? '';
  const canStart = !!options && options.tracks.length > 0 && !checkingMic;

  return (
    <div className={`live-setup ${theme}`}>
      <h2 className="live-setup__title">Choose your interview</h2>
      {setupNotice && (
        <p role="status" className="live-setup__notice">
          {setupNotice}
        </p>
      )}

      {optionsLoading && (
        <div aria-label="Loading interview options">
          <div className="live-setup__tracks">
            <div className="track-card track-card__skeleton" aria-hidden="true" />
            <div className="track-card track-card__skeleton" aria-hidden="true" />
          </div>
          <div className="duration-picker duration-picker--disabled" aria-hidden="true" />
        </div>
      )}

      {!optionsLoading && optionsError && (
        <div className="live-setup__empty">
          <p>We couldn&apos;t load interview options.</p>
          <button type="button" className="live-setup__retry" onClick={onRetryOptions}>
            Try again
          </button>
        </div>
      )}

      {!optionsLoading && !optionsError && options && options.tracks.length === 0 && (
        <p className="live-setup__empty">No interview types are available right now. Please try again later.</p>
      )}

      {!optionsLoading && !optionsError && selectedTrack && (
        <>
          <div className="live-setup__tracks" role="radiogroup" aria-label="Interview type">
            {tracks.map((track) => (
              <TrackCard
                key={track.type}
                track={track}
                selected={track.type === selectedTrack.type}
                durationMinutes={durationMinutes}
                onSelect={() => onTrackTypeChange(track.type)}
                isDarkMode={isDarkMode}
              />
            ))}
          </div>

          <div className="live-setup__length">
            <span id="interview-length-label" className="live-setup__label">
              Length
            </span>
            <DurationPicker
              durations={options?.durations_minutes ?? []}
              selected={durationMinutes}
              onSelect={onDurationChange}
              disabled={false}
              isDarkMode={isDarkMode}
            />
          </div>

          <p className="live-setup__summary">
            {interviewerName} will run a {durationMinutes}-minute {selectedTrack.title} interview. Think out
            loud like you would with a real interviewer. Share your screen when you want her to see your
            diagram or code.
          </p>

          <button type="button" className="live-setup__start" disabled={!canStart} onClick={onStart}>
            {checkingMic ? 'Checking your microphone…' : 'Start interview'}
          </button>

          {micProblem === 'denied' && (
            <div className="live-setup__mic-error">
              <p>
                {interviewerName} can&apos;t hear you yet. Allow microphone access from the icon in your
                browser&apos;s address bar, then try again.
              </p>
              <button type="button" className="live-setup__retry" onClick={onStart}>
                Try again
              </button>
            </div>
          )}
          {micProblem === 'not-found' && (
            <p className="live-setup__mic-error">We couldn&apos;t find a microphone. Plug one in and try again.</p>
          )}
        </>
      )}
    </div>
  );
}
