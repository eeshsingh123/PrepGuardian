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
}

export function ConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  isDarkMode
}: ConfirmationModalProps) {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className={`modal-content ${isDarkMode ? 'modal-content--dark' : 'modal-content--light'}`}>
        <button className="modal-close" onClick={onClose} aria-label="Close">
          <X size={20} />
        </button>
        
        <div className="modal-body">
          <div className="modal-icon text-red-500">
            <AlertCircle size={40} />
          </div>
          
          <h3 className="modal-title">{title}</h3>
          <p className="modal-message">{message}</p>
          
          <div className="modal-actions">
            <button 
              className={`modal-btn modal-btn--cancel ${isDarkMode ? 'modal-btn--cancel-dark' : 'modal-btn--cancel-light'}`}
              onClick={onClose}
            >
              {cancelText}
            </button>
            <button 
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
