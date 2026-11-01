import { useEffect, useState } from 'react';
import type { Attachment } from '@/types';
import { Dialog, DialogContent, DialogTitle } from './ui/dialog';

/** Shared thumbnail for pending uploads, persisted chat and design sources. */
export function AttachmentPreview({ attachment }: { attachment: Attachment }) {
  const [local, setLocal] = useState<string>();
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const image = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(attachment.type);
  useEffect(() => {
    if (!image || !attachment.file) return;
    const url = URL.createObjectURL(attachment.file);
    setLocal(url);
    return () => URL.revokeObjectURL(url);
  }, [attachment.file, image]);
  const src = attachment.file ? local : /^att-[a-f0-9]{12}$/.test(attachment.id)
    ? `/api/attachments/${attachment.id}` : undefined;
  if (!image) return <span className="text-xs break-all">{attachment.name}</span>;
  return <>
    <button type="button" onClick={() => setOpen(true)} aria-label={`Agrandir ${attachment.name}`}
      className="flex items-center gap-2 rounded-xl p-1 text-left max-w-full hover:bg-white/10 transition-colors">
      {src && !failed ? <img src={src} alt={attachment.name} onError={() => setFailed(true)}
        className="h-16 w-20 rounded-lg object-contain bg-white/5" />
        : <span className="text-xs p-2">{failed ? 'Image indisponible' : 'Chargement…'}</span>}
      <span className="text-xs truncate max-w-40">{attachment.name}</span>
    </button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-[90vw] max-h-[92vh] overflow-auto bg-[var(--bg-surface)] text-[var(--text-primary)]" aria-describedby={undefined}>
        <DialogTitle>{attachment.name}</DialogTitle>
        {src && !failed ? <img src={src} alt={attachment.name} className="w-full max-h-[78vh] object-contain" onError={() => setFailed(true)} />
          : <p role="status">Cette image est indisponible. Joins-la à nouveau pour la consulter.</p>}
      </DialogContent>
    </Dialog>
  </>;
}
