// Modal shown on an Forge host to confirm auto-selecting the detected board

import { useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { ImageOff } from 'lucide-react';
import { BoardBadges } from '../shared/BoardBadges';
import type { ForgeReleaseInfo, BoardInfo } from '../../types';
import { setForgeBoardDetection } from '../../hooks/useSettings';
import { useModalExitAnimation } from '../../hooks/useModalExitAnimation';

interface ForgeBoardModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  onDetectionDisabled?: () => void;
  ForgeInfo: ForgeReleaseInfo;
  boardInfo?: BoardInfo | null;
  boardImageUrl?: string | null;
}

export function ForgeBoardModal({
  isOpen,
  onClose,
  onConfirm,
  onDetectionDisabled,
  ForgeInfo,
  boardInfo,
  boardImageUrl,
}: ForgeBoardModalProps) {
  const { t } = useTranslation();

  const { isExiting, handleClose, handleAction } = useModalExitAnimation({
    onClose,
    duration: 200,
    onExiting: () => {
      // 'auto' enables silent auto-selection on future runs
      setForgeBoardDetection('auto');
    },
  });

  const handleConfirm = useCallback(() => {
    handleAction(() => {
      onConfirm();
    });
  }, [handleAction, onConfirm]);

  const handleCloseWithCallback = useCallback(() => {
    handleAction(() => {
      setForgeBoardDetection('disabled');
      onDetectionDisabled?.();
    });
  }, [handleAction, onDetectionDisabled]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isExiting) {
        handleCloseWithCallback();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, isExiting, handleCloseWithCallback]);

  if (!isOpen) return null;

  const animationClass = isExiting ? 'modal-exiting' : 'modal-entering';

  return (
    <div className={`modal-overlay ${animationClass}`} onClick={handleClose}>
      <div
        className={`modal modal-compact Forge-modal ${animationClass}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="Forge-board-name"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="Forge-board-close" onClick={handleClose} aria-label="Close">
          ✕
        </button>

        <div className="modal-body Forge-board-modal">
          <div className="Forge-board-hero">
            <div className="Forge-board-image">
              {boardImageUrl ? (
                <img src={boardImageUrl} alt={ForgeInfo.board_name} />
              ) : (
                <div className="board-image-placeholder">
                  <ImageOff size={40} />
                </div>
              )}
            </div>
          </div>

          <h3 id="Forge-board-name" className="Forge-board-name">{ForgeInfo.board_name}</h3>

          {boardInfo && <BoardBadges board={boardInfo} className="centered" />}

          <p className="Forge-board-description">{t('Forge.description')}</p>

          <div className="Forge-board-actions">
            <button className="btn btn-secondary" onClick={handleCloseWithCallback} disabled={isExiting}>
              {t('common.cancel')}
            </button>
            <button className="btn btn-primary" onClick={handleConfirm} disabled={isExiting}>
              {t('common.confirm')}
            </button>
          </div>
          <p className="Forge-board-hint">{t('Forge.cancelHint')}</p>
        </div>
      </div>
    </div>
  );
}
