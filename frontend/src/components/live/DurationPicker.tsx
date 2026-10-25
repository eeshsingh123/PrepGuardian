interface DurationPickerProps {
  durations: number[];
  selected: number;
  onSelect: (minutes: number) => void;
  disabled: boolean;
  isDarkMode: boolean;
}

export function DurationPicker({ durations, selected, onSelect, disabled, isDarkMode }: DurationPickerProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Interview length"
      className={`duration-picker ${isDarkMode ? 'duration-picker--dark' : 'duration-picker--light'}`}
    >
      {durations.map((minutes) => (
        <label
          key={minutes}
          className={`duration-picker__option${selected === minutes ? ' duration-picker__option--selected' : ''}${disabled ? ' duration-picker__option--disabled' : ''}`}
        >
          <input
            type="radio"
            name="interview-duration"
            className="duration-picker__input"
            checked={selected === minutes}
            disabled={disabled}
            onChange={() => onSelect(minutes)}
            aria-label={`${minutes} minutes`}
          />
          <span>{minutes} min</span>
        </label>
      ))}
    </div>
  );
}
