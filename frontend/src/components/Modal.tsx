import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react';
import type { ReactNode } from 'react';
export function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <Dialog open onClose={onClose} className="modal-container">
      <div className="modal-overlay" aria-hidden="true" />
      <div className="modal-position">
        <DialogPanel className={`modal-content ${wide ? 'modal-wide' : ''}`}>
          <div className="modal-heading">
            <DialogTitle as="h2">{title}</DialogTitle>
            <button onClick={onClose} aria-label="Close dialog" className="icon-button">
              ×
            </button>
          </div>
          {children}
        </DialogPanel>
      </div>
    </Dialog>
  );
}
