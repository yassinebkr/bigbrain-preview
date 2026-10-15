import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  FolderPlus,
  Sparkles,
  Import,
  Settings,
  X,
  Check,
  ArrowUpFromLine,
} from 'lucide-react';
import { useAppStore } from '@/store/appStore';

interface QuickAction {
  id: string;
  label: string;
  icon: React.ReactNode;
  shortcut?: string;
  onClick: () => void;
}

export function QuickActions() {
  const { addFile, setView } = useAppStore();
  const [showNewDocDialog, setShowNewDocDialog] = useState(false);
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [newName, setNewName] = useState('');
  const [justCreated, setJustCreated] = useState<string | null>(null);

  const handleNewDocument = () => {
    if (!newName.trim()) return;
    const file = {
      id: `file-${Date.now()}`,
      name: newName.trim().endsWith('.md') || newName.trim().endsWith('.txt')
        ? newName.trim()
        : `${newName.trim()}.md`,
      type: 'file' as const,
      size: 0,
      modifiedAt: Date.now(),
      parentId: null,
      icon: 'file-text',
    };
    addFile(file);
    setJustCreated(file.id);
    setTimeout(() => setJustCreated(null), 2000);
    setNewName('');
    setShowNewDocDialog(false);
  };

  const handleNewFolder = () => {
    if (!newName.trim()) return;
    const folder = {
      id: `folder-${Date.now()}`,
      name: newName.trim(),
      type: 'folder' as const,
      modifiedAt: Date.now(),
      parentId: null,
    };
    addFile(folder);
    setJustCreated(folder.id);
    setTimeout(() => setJustCreated(null), 2000);
    setNewName('');
    setShowNewFolderDialog(false);
  };

  const actions: QuickAction[] = [
    {
      id: 'new-doc',
      label: 'New Document',
      icon: <FileText size={16} strokeWidth={1.5} />,
      shortcut: 'Ctrl+N',
      onClick: () => {
        setNewName('');
        setShowNewDocDialog(true);
      },
    },
    {
      id: 'new-folder',
      label: 'New Folder',
      icon: <FolderPlus size={16} strokeWidth={1.5} />,
      onClick: () => {
        setNewName('');
        setShowNewFolderDialog(true);
      },
    },
    {
      id: 'ai-assist',
      label: 'AI Assistant',
      icon: <Sparkles size={16} strokeWidth={1.5} />,
      onClick: () => {
        setView('chat');
      },
    },
    {
      id: 'import',
      label: 'Import',
      icon: <Import size={16} strokeWidth={1.5} />,
      onClick: () => {
        // Trigger file input
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.onchange = (e) => {
          const files = (e.target as HTMLInputElement).files;
          if (files) {
            Array.from(files).forEach((f) => {
              const fileItem = {
                id: `file-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                name: f.name,
                type: 'file' as const,
                size: f.size,
                modifiedAt: Date.now(),
                parentId: null,
                icon: f.name.endsWith('.png') || f.name.endsWith('.jpg') || f.name.endsWith('.svg')
                  ? 'image'
                  : f.name.endsWith('.tsx') || f.name.endsWith('.ts') || f.name.endsWith('.js')
                  ? 'code'
                  : 'file-text',
              };
              addFile(fileItem);
            });
          }
        };
        input.click();
      },
    },
    {
      id: 'export',
      label: 'Export',
      icon: <ArrowUpFromLine size={16} strokeWidth={1.5} />,
      onClick: () => {
        const { tasks, files } = useAppStore.getState();
        const data = {
          exportDate: new Date().toISOString(),
          tasks,
          files,
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `workspace-export-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
      },
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: <Settings size={16} strokeWidth={1.5} />,
      onClick: () => {
        useAppStore.getState().toggleSidebarPanel('settings');
      },
    },
  ];

  return (
    <>
      <div
        className="flex items-center gap-1 px-3 py-1.5 border-b"
        style={{
          borderColor: 'var(--border-subtle)',
          backgroundColor: 'var(--bg-primary)',
        }}
      >
        {actions.map((action, index) => (
          <motion.button
            key={action.id}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: index * 0.04 }}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
            onClick={action.onClick}
            className="flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-colors duration-150 cursor-pointer border h-9"
            style={{
              backgroundColor: 'var(--bg-surface)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-secondary)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
              e.currentTarget.style.color = 'var(--text-primary)';
              e.currentTarget.style.borderColor = 'var(--border-input)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-surface)';
              e.currentTarget.style.color = 'var(--text-secondary)';
              e.currentTarget.style.borderColor = 'var(--border-subtle)';
            }}
            title={action.shortcut ? `${action.label} (${action.shortcut})` : action.label}
          >
            <span style={{ color: 'var(--text-tertiary)' }}>{action.icon}</span>
            <span className="hidden sm:inline">{action.label}</span>
          </motion.button>
        ))}

        <AnimatePresence>
          {justCreated && (
            <motion.div
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              className="ml-auto flex items-center gap-1 text-[11px] font-medium"
              style={{ color: '#34c759' }}
            >
              <Check size={12} />
              Created
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* New Document Dialog */}
      <AnimatePresence>
        {showNewDocDialog && (
          <Dialog
            title="New Document"
            value={newName}
            onChange={setNewName}
            onSubmit={handleNewDocument}
            onCancel={() => setShowNewDocDialog(false)}
            placeholder="Document name..."
          />
        )}
      </AnimatePresence>

      {/* New Folder Dialog */}
      <AnimatePresence>
        {showNewFolderDialog && (
          <Dialog
            title="New Folder"
            value={newName}
            onChange={setNewName}
            onSubmit={handleNewFolder}
            onCancel={() => setShowNewFolderDialog(false)}
            placeholder="Folder name..."
          />
        )}
      </AnimatePresence>
    </>
  );
}

function Dialog({
  title,
  value,
  onChange,
  onSubmit,
  onCancel,
  placeholder,
}: {
  title: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  placeholder: string;
}) {
  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 bg-black/40"
        onClick={onCancel}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.15 }}
        className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-sm rounded-xl border p-5 shadow-2xl"
        style={{
          backgroundColor: 'var(--bg-surface)',
          borderColor: 'var(--border-subtle)',
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3
            className="text-sm font-semibold"
            style={{ color: 'var(--text-primary)' }}
          >
            {title}
          </h3>
          <button
            onClick={onCancel}
            className="p-1 rounded cursor-pointer"
            style={{ color: 'var(--text-tertiary)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <X size={14} />
          </button>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
        >
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            autoFocus
            className="w-full rounded-lg px-3 py-2 text-sm outline-none mb-4 transition-shadow duration-200"
            style={{
              backgroundColor: 'var(--bg-input)',
              border: '1px solid var(--border-input)',
              color: 'var(--text-primary)',
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = 'var(--accent-blue)';
              e.currentTarget.style.boxShadow = '0 0 0 2px rgba(0,113,227,0.2)';
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-input)';
              e.currentTarget.style.boxShadow = 'none';
            }}
          />
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer"
              style={{
                backgroundColor: 'var(--bg-pill)',
                color: 'var(--text-secondary)',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!value.trim()}
              className="px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40 cursor-pointer"
              style={{
                backgroundColor: 'var(--accent-blue)',
                color: '#fff',
              }}
            >
              Create
            </button>
          </div>
        </form>
      </motion.div>
    </>
  );
}
