import { ConnectionBanner } from './ConnectionBanner';
import { SetupPanel } from './SetupPanel';
import type { UseLiveSession } from './useLiveSession';

interface SetupScreenProps {
  live: UseLiveSession;
  isDarkMode: boolean;
}

export function SetupScreen({ live, isDarkMode }: SetupScreenProps) {
  return (
    <div className="voice-agent">
      <span aria-live="polite" className="sr-only">
        {live.announcement?.text ?? ''}
      </span>
      {live.banner && (
        <ConnectionBanner
          message={live.banner.message}
          showRetry={live.banner.showRetry}
          showSetup={live.banner.showSetup}
          showTranscripts={live.banner.showTranscripts}
          onRetry={live.retry}
          onSetup={live.backToSetup}
          onTranscripts={live.goToTranscripts}
        />
      )}
      <SetupPanel
        options={live.options}
        optionsLoading={live.optionsLoading}
        optionsError={live.optionsError}
        onRetryOptions={() => void live.reloadOptions()}
        trackType={live.resolvedChoice?.trackType ?? ''}
        durationMinutes={live.resolvedChoice?.durationMinutes ?? 0}
        onTrackTypeChange={(trackType) =>
          live.resolvedChoice && live.setChoice({ ...live.resolvedChoice, trackType })
        }
        onDurationChange={(durationMinutes) =>
          live.resolvedChoice && live.setChoice({ ...live.resolvedChoice, durationMinutes })
        }
        checkingMic={live.checkingMic}
        creatingSession={live.creatingSession}
        micProblem={live.micProblem}
        setupNotice={live.setupNotice}
        onStart={() => void live.start()}
        isDarkMode={isDarkMode}
      />
    </div>
  );
}
