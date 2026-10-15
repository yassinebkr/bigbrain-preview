import { X, File } from 'lucide-react';
import type { Attachment } from '@/types';

interface AttachmentChipProps {
  attachment: Attachment;
  onRemove: (id: string) => void;
}

export function AttachmentChip({ attachment, onRemove }: AttachmentChipProps) {
  return (
    <div
      className="flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs"
      style={{
        backgroundColor: 'var(--bg-button)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <File size={14} style={{ color: 'var(--text-tertiary)' }} />
      <span
        className="max-w-[120px] truncate"
        style={{ color: 'var(--text-primary)' }}
      >
        {attachment.name}
      </span>
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
