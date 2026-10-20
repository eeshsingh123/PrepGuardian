import { useEffect, useRef } from 'react';
import { LogOut, Mic, MicOff, MonitorOff, MonitorUp, Volume2, VolumeX } from 'lucide-react';
import { ConfirmationModal } from './ConfirmationModal';
import { ConnectionBanner } from './live/ConnectionBanner';
import { InterviewerBadge, type BadgeStatus } from './live/InterviewerBadge';
import { PhaseProgress } from './live/PhaseProgress';
import { SessionTimer } from './live/SessionTimer';
import { SetupScreen } from './live/SetupScreen';
import { useLiveSession } from './live/useLiveSession';

interface VoiceAgentProps {
  isDarkMode: boolean;
  onSessionEnded?: () => void;
  onLiveChange?: (isLive: boolean) => void;
  endRequestRef?: { current: (() => void) | null };
}

export function VoiceAgent({ isDarkMode, onSessionEnded, onLiveChange, endRequestRef }: VoiceAgentProps) {
  const previewVideoRef = useRef<HTMLVideoElement | null>(null);
  const live = useLiveSession({ onSessionEnded, previewVideoRef });
  const inSession = live.phase === 'live' || live.phase === 'connecting';

  useEffect(() => {
    onLiveChange?.(inSession);
  }, [inSession, onLiveChange]);

  useEffect(() => {
    if (!endRequestRef) return;
    endRequestRef.current = live.requestEnd;
    return () => {
      endRequestRef.current = null;
    };
  }, [endRequestRef, live.requestEnd]);

  if (live.phase === 'setup') {
    return <SetupScreen live={live} isDarkMode={isDarkMode} />;
  }

  const badgeStatus: BadgeStatus =
    live.phase !== 'live' ? 'connecting'
    : !live.joined ? 'joining'
    : live.muted ? 'muted'
    : live.agentVoice === 'agent_speaking' ? 'speaking' : 'listening';
  const orbState = live.phase !== 'live' ? 'disconnected' : live.agentVoice;
  const controlsDisabled = live.phase !== 'live' || live.banner?.kind === 'fatal';

  return (
    <div className="voice-agent live">
      <span aria-live="polite" className="sr-only">
        {live.announcement?.text ?? ''}
      </span>
      {live.banner && (
        <ConnectionBanner
          message={live.banner.message}
          showRetry={live.banner.showRetry}
          showSetup={live.banner.showSetup}
          showTranscripts={live.banner.showTranscripts}
          onRetry={() => live.retry()}
          onSetup={live.backToSetup}
          onTranscripts={live.goToTranscripts}
        />
      )}
      <div className="live__header">
        <InterviewerBadge name={live.interviewerName} status={badgeStatus} />
        <SessionTimer
          remainingSeconds={live.remainingSeconds}
          timeUp={live.timeUp}
          connected={live.phase === 'live'}
          isDarkMode={isDarkMode}
        />
      </div>
      {live.selectedTrack && (
        <PhaseProgress
          track={live.selectedTrack}
          durationMinutes={live.resolvedChoice?.durationMinutes ?? 0}
          currentIndex={live.clock?.phase_index ?? 0}
          currentFill={live.currentFill}
          ready={live.phase === 'live'}
          isDarkMode={isDarkMode}
        />
      )}
      <div className="voice-agent__orb-container">
        <div className={`orb orb--${orbState} ${isDarkMode ? 'orb--dark' : 'orb--light'}`} aria-hidden="true">
          <div className="orb__ring orb__ring--1" />
          <div className="orb__ring orb__ring--2" />
          <div className="orb__ring orb__ring--3" />
          <div className="orb__core" />
        </div>
        <div className={`voice-agent__state-label ${isDarkMode ? 'text-gray-500' : 'text-gray-400'}`}>
          {live.phase === 'connecting' && `Connecting to ${live.interviewerName}…`}
          {live.phase === 'ending' && 'Wrapping up… saving your transcript'}
          {live.phase === 'live' && live.agentVoice === 'idle' && 'Ready to listen'}
          {live.phase === 'live' && live.agentVoice === 'listening' && 'Listening…'}
          {live.phase === 'live' && live.agentVoice === 'agent_speaking' && 'Speaking…'}
        </div>
      </div>
      <div className={`voice-agent__transcript ${isDarkMode ? 'voice-agent__transcript--dark' : 'voice-agent__transcript--light'}`}>
        {live.transcript ? (
          <p className="voice-agent__transcript-text">{live.transcript}</p>
        ) : (
          <p className="voice-agent__transcript-placeholder">Session captions will appear here</p>
        )}
      </div>
      {live.isSharing && (
        <>
          <span className="live__sharing-pill">Sharing</span>
            <div className="live__preview">
              <video ref={previewVideoRef} autoPlay muted playsInline className="live__preview-video" />
            <span className="live__preview-badge">Sharing</span>
          </div>
        </>
      )}
      <div className={`voice-agent__controls ${isDarkMode ? 'voice-agent__controls--dark' : 'voice-agent__controls--light'}`}>
        <button
          type="button"
          className={`voice-agent__btn voice-agent__btn--secondary ${live.isSharing ? 'voice-agent__btn--active' : ''} ${isDarkMode ? 'voice-agent__btn--dark' : 'voice-agent__btn--light'}`}
          onClick={() => void live.toggleShare()}
          disabled={controlsDisabled || !live.shareSupported}
          title={live.shareSupported ? (live.isSharing ? 'Stop sharing (S)' : 'Share screen (S)') : "Screen sharing isn't available on this device"}
          aria-label={live.isSharing ? 'Stop sharing screen' : 'Share screen'}
        >
          {live.isSharing ? <MonitorUp className="voice-agent__btn-icon" /> : <MonitorOff className="voice-agent__btn-icon" />}
        </button>
        <button
          type="button"
          className={`voice-agent__btn voice-agent__btn--mic ${!live.muted ? 'voice-agent__btn--mic-active' : ''} ${isDarkMode ? 'voice-agent__btn--mic-dark' : 'voice-agent__btn--mic-light'}`}
          onClick={live.toggleMute}
          disabled={controlsDisabled}
          title={live.muted ? 'Unmute (M)' : 'Mute (M)'}
          aria-label={live.muted ? 'Unmute microphone' : 'Mute microphone'}
          aria-pressed={live.muted}
        >
          {live.muted ? <MicOff className="voice-agent__btn-icon--lg" /> : <Mic className="voice-agent__btn-icon--lg" />}
        </button>
        <button
          type="button"
          className={`voice-agent__btn voice-agent__btn--secondary ${live.speakerMuted ? 'voice-agent__btn--active' : ''} ${isDarkMode ? 'voice-agent__btn--dark' : 'voice-agent__btn--light'}`}
          onClick={live.toggleSpeaker}
          disabled={controlsDisabled}
          title={live.speakerMuted ? 'Unmute speaker' : 'Mute speaker'}
          aria-label={live.speakerMuted ? 'Unmute speaker' : 'Mute speaker'}
        >
          {live.speakerMuted ? <VolumeX className="voice-agent__btn-icon" /> : <Volume2 className="voice-agent__btn-icon" />}
        </button>
      </div>
      {live.shareProblem && (
        <p role="status" className="live__share-error">
          {live.shareProblem}
        </p>
      )}
      <div className="voice-agent__end-session-container">
        {live.phase === 'connecting' ? (
          <button
            type="button"
            className={`voice-agent__end-btn ${isDarkMode ? 'voice-agent__end-btn--dark' : 'voice-agent__end-btn--light'}`}
            onClick={live.requestEnd}
            aria-label="Cancel connecting"
          >
            Cancel
          </button>
        ) : (
          <button
            type="button"
            className={`voice-agent__end-btn ${isDarkMode ? 'voice-agent__end-btn--dark' : 'voice-agent__end-btn--light'}`}
            onClick={live.requestEnd}
            disabled={live.phase !== 'live'}
            title="End interview (E)"
            aria-label="End interview"
          >
            <LogOut size={16} className="mr-2" />
            <span>{live.phase === 'ending' ? 'Wrapping up…' : 'End interview'}</span>
          </button>
        )}
      </div>
      <p className="live__shortcuts" aria-hidden="true">M mute · S share · E end</p>
      <ConfirmationModal
        isOpen={live.showEndModal}
        onClose={() => live.setShowEndModal(false)}
        onConfirm={live.confirmEnd}
        title="End the interview?"
        message={`${live.interviewerName} will stop here and your transcript will be saved. You can get feedback on it afterwards.`}
        confirmText="End interview"
        cancelText="Keep going"
        isDarkMode={isDarkMode}
        initialFocus="cancel"
      />
    </div>
  );
}
