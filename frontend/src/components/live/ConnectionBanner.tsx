interface ConnectionBannerProps {
  message: string;
  showRetry: boolean;
  showSetup: boolean;
  showTranscripts: boolean;
  onRetry: () => void;
  onSetup: () => void;
  onTranscripts: () => void;
}

export function ConnectionBanner({
  message,
  showRetry,
  showSetup,
  showTranscripts,
  onRetry,
  onSetup,
  onTranscripts,
}: ConnectionBannerProps) {
  return (
    <div role="alert" className="connection-banner">
      <p className="connection-banner__message">{message}</p>
      <div className="connection-banner__actions">
        {showRetry && (
          <button type="button" className="connection-banner__btn" onClick={onRetry}>
            Try again
          </button>
        )}
        {showSetup && (
          <button type="button" className="connection-banner__btn" onClick={onSetup}>
            Back to setup
          </button>
        )}
        {showTranscripts && (
          <button type="button" className="connection-banner__btn" onClick={onTranscripts}>
            View transcripts
          </button>
        )}
      </div>
    </div>
  );
}
