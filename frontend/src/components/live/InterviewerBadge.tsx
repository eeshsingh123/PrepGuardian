export type BadgeStatus = 'speaking' | 'listening' | 'muted' | 'connecting';

interface InterviewerBadgeProps {
  name: string;
  status: BadgeStatus;
}

const STATUS_COPY: Record<BadgeStatus, string> = {
  speaking: 'Speaking',
  listening: 'Listening',
  muted: "You're muted",
  connecting: 'Connecting…',
};

export function InterviewerBadge({ name, status }: InterviewerBadgeProps) {
  return (
    <div className="interviewer-badge">
      <span aria-hidden="true" className={`interviewer-badge__avatar interviewer-badge__avatar--${status}`}>
        {name.charAt(0).toUpperCase()}
      </span>
      <span className="interviewer-badge__text">
        <span className="interviewer-badge__name">{name}</span>
        <span className="interviewer-badge__status">{STATUS_COPY[status]}</span>
      </span>
    </div>
  );
}
