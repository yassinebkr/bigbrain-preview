import { X, File } from 'lucide-react';
import type { Attachment } from '@/types';
import { AttachmentPreview } from './AttachmentPreview';

interface AttachmentChipProps {
  attachment: Attachment;
  onRemove: (id: string) => void;
}

export function AttachmentChip({ attachment, onRemove }: AttachmentChipProps) {
  return (
    <div
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs"
      style={{
        backgroundColor: 'var(--bg-button)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      {!attachment.type.startsWith('image/') && <File size={14} style={{ color: 'var(--text-tertiary)' }} />}
      <AttachmentPreview attachment={attachment} />
      <button
        onClick={() => onRemove(attachment.id)}
        className="ml-0.5 p-0.5 rounded hover:opacity-70 transition-opacity"
        aria-label="Remove attachment"
      >
        <X size={12} style={{ color: 'var(--text-tertiary)' }} />
      </button>
    </div>
  );
}
