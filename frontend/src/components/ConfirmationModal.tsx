import { useEffect, useId, useRef } from 'react';
import { AlertCircle, X } from 'lucide-react';

interface ConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  isDarkMode: boolean;
  initialFocus?: 'cancel' | 'confirm';
}

export function ConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  isDarkMode,
  initialFocus = 'cancel',
}: ConfirmationModalProps) {
  const titleId = useId();
  const overlayRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    (initialFocus === 'confirm' ? confirmRef : cancelRef).current?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== 'Tab' || !overlayRef.current) return;
      const focusables = Array.from(
        overlayRef.current.querySelectorAll<HTMLElement>(
          'button:not(:disabled), [href], input:not(:disabled), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      previouslyFocused?.focus?.();
    };
  }, [isOpen, initialFocus]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" ref={overlayRef}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`modal-content ${isDarkMode ? 'modal-content--dark' : 'modal-content--light'}`}
      >
        <button className="modal-close" onClick={onClose} aria-label="Close">
          <X size={20} />
        </button>

        <div className="modal-body">
          <div className="modal-icon text-red-500">
            <AlertCircle size={40} />
          </div>

          <h3 id={titleId} className="modal-title">{title}</h3>
          <p className="modal-message">{message}</p>

          <div className="modal-actions">
            <button
              ref={cancelRef}
              className={`modal-btn modal-btn--cancel ${isDarkMode ? 'modal-btn--cancel-dark' : 'modal-btn--cancel-light'}`}
              onClick={onClose}
            >
              {cancelText}
            </button>
            <button
              ref={confirmRef}
              className="modal-btn modal-btn--confirm"
              onClick={onConfirm}
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
