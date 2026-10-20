import { Clock } from 'lucide-react';

interface SessionTimerProps {
  remainingSeconds: number;
  timeUp: boolean;
  connected: boolean;
  isDarkMode: boolean;
}

function formatTimer(remainingSeconds: number, timeUp: boolean, connected: boolean): string {
  if (!connected) return '--:--';
  if (timeUp) return "Time's up";
  const clamped = Math.max(0, Math.floor(remainingSeconds));
  const mins = Math.floor(clamped / 60);
  const secs = clamped % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function timerTone(remainingSeconds: number): string {
  if (remainingSeconds <= 3 * 60) return 'red';
  if (remainingSeconds <= 10 * 60) return 'orange';
  return 'green';
}

export function SessionTimer({ remainingSeconds, timeUp, connected, isDarkMode }: SessionTimerProps) {
  return (
    <div
      aria-hidden="true"
      className={`voice-agent__timer voice-agent__timer--${isDarkMode ? 'dark' : 'light'} voice-agent__timer--${timerTone(remainingSeconds)}`}
    >
      <Clock className="voice-agent__timer-icon" />
      <span className="voice-agent__timer-label">Time left</span>
      <span className="voice-agent__timer-value">{formatTimer(remainingSeconds, timeUp, connected)}</span>
    </div>
  );
}
