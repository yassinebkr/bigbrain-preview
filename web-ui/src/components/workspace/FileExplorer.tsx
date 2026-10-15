import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Folder,
  FileText,
  Image,
  Code,
  File,
  ChevronRight,
  ChevronDown,
  Home,
  Trash2,
  Download,
  FolderOpen,
  Search,
  ArrowLeft,
  ExternalLink,
} from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import type { FileItem } from '@/types';

const folderIcons: Record<string, React.ReactNode> = {
  root: <Home size={16} strokeWidth={1.5} />,
  docs: <Folder size={16} strokeWidth={1.5} />,
  proj: <Folder size={16} strokeWidth={1.5} />,
  research: <Folder size={16} strokeWidth={1.5} />,
  dl: <Download size={16} strokeWidth={1.5} />,
  trash: <Trash2 size={16} strokeWidth={1.5} />,
};

const fileIcons: Record<string, React.ReactNode> = {
  'file-text': <FileText size={18} strokeWidth={1.5} />,
  code: <Code size={18} strokeWidth={1.5} />,
  image: <Image size={18} strokeWidth={1.5} />,
  file: <File size={18} strokeWidth={1.5} />,
};

const fileColors: Record<string, string> = {
  'file-text': '#5ac8fa',
  code: '#34c759',
  image: '#ff9500',
  file: '#a1a1aa',
};

function formatBytes(bytes?: number): string {
  if (bytes === undefined) return '--';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatDate(timestamp: number): string {
  const d = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffHrs = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffHrs < 1) return 'Just now';
  if (diffHrs < 24) return diffHrs + 'h ago';
  if (diffDays < 7) return diffDays + 'd ago';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Tree item component
function TreeItem({
  folder,
  depth,
  isOpen,
  onToggle,
  isSelected,
  onSelect,
}: {
  folder: FileItem;
  depth: number;
  isOpen: boolean;
  onToggle: () => void;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const icon = folderIcons[folder.id] || <Folder size={16} strokeWidth={1.5} />;

  return (
    <div>
      <motion.button
        whileTap={{ scale: 0.98 }}
        onClick={() => {
          onSelect();
          onToggle();
        }}
        className="flex items-center w-full py-1.5 pr-2 text-sm transition-colors duration-150 cursor-pointer relative"
        style={{
          paddingLeft: `${depth * 12 + 8}px`,
          backgroundColor: isSelected ? 'rgba(0,113,227,0.1)' : 'transparent',
          borderLeft: isSelected ? '2px solid var(--accent-blue)' : '2px solid transparent',
          color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)',
        }}
        onMouseEnter={(e) => {
          if (!isSelected) {
            e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
            e.currentTarget.style.color = 'var(--text-primary)';
          }
        }}
        onMouseLeave={(e) => {
          if (!isSelected) {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }
        }}
      >
        <span
          className="flex items-center justify-center w-4 h-4 mr-1 flex-shrink-0"
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
          style={{ color: 'var(--text-tertiary)' }}
        >
          {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
        <span
          className="mr-2 flex-shrink-0"
          style={{
            color: folder.id === 'trash' ? '#ff453a' : folder.id === 'dl' ? '#5ac8fa' : '#0071e3',
          }}
        >
          {isOpen && (folder.id === 'docs' || folder.id === 'proj' || folder.id === 'research' || folder.id === 'dl' || folder.id === 'trash' || folder.id === 'root')
            ? <FolderOpen size={16} strokeWidth={1.5} />
            : icon}
        </span>
        <span className="truncate">{folder.name}</span>
      </motion.button>
    </div>
  );
}

// Context menu component
function ContextMenu({
  x,
  y,
  onClose,
  onAction,
}: {
  x: number;
  y: number;
  onClose: () => void;
  onAction: (action: string) => void;
}) {
  const items = [
    { id: 'open', label: 'Open' },
    { id: 'rename', label: 'Rename' },
    { id: 'copy', label: 'Copy' },
    { id: 'move', label: 'Move to...' },
    { id: 'delete', label: 'Move to Trash' },
  ];

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.1 }}
        className="fixed z-50 py-1 rounded-lg shadow-lg border"
        style={{
          top: y,
          left: x,
          backgroundColor: 'var(--bg-surface)',
          borderColor: 'var(--border-subtle)',
          minWidth: '160px',
        }}
      >
        {items.map((item) => (
          <button
            key={item.id}
            onClick={() => {
              onAction(item.id);
              onClose();
            }}
            className="w-full text-left px-3 py-1.5 text-sm transition-colors duration-100 cursor-pointer"
            style={{
              color: item.id === 'delete' ? '#ff453a' : 'var(--text-primary)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            {item.label}
          </button>
        ))}
      </motion.div>
    </>
  );
}

export function FileExplorer() {
  const { files, selectedFileId, setSelectedFileId, setWorkspaceView } = useAppStore();
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['root', 'docs', 'proj']));
  const [searchQuery, setSearchQuery] = useState('');
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<FileItem | null>(null);

  const rootFolders = useMemo(() => files.filter((f) => f.type === 'folder'), [files]);

  const currentFiles = useMemo(() => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return files.filter(
        (f) =>
          f.type === 'file' &&
          f.name.toLowerCase().includes(q)
      );
    }
    return files.filter((f) => f.parentId === currentFolderId);
  }, [files, currentFolderId, searchQuery]);

  const breadcrumb = useMemo(() => {
    const path: FileItem[] = [];
    let current = currentFolderId;
    while (current) {
      const folder = files.find((f) => f.id === current);
      if (folder) {
        path.unshift(folder);
        current = folder.parentId;
      } else {
        break;
      }
    }
    return path;
  }, [currentFolderId, files]);

  const toggleFolder = (id: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const navigateToFolder = (id: string | null) => {
    setCurrentFolderId(id);
    setViewingFile(null);
    setWorkspaceView('files');
  };

  const openFile = (file: FileItem) => {
    setSelectedFileId(file.id);
    setViewingFile(file);
    setWorkspaceView('files');
  };

  const openFolder = (folder: FileItem) => {
    setCurrentFolderId(folder.id);
    setExpandedFolders((prev) => new Set([...prev, folder.id]));
    setViewingFile(null);
    setWorkspaceView('files');
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  // If viewing a file, show file viewer
  if (viewingFile) {
    return (
      <div className="flex h-full w-full flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
        {/* File viewer header */}
        <div
          className="flex items-center px-3 py-2 border-b gap-2 flex-shrink-0"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <button
            onClick={() => setViewingFile(null)}
            className="p-1 rounded transition-colors duration-100 cursor-pointer flex-shrink-0"
            style={{ color: 'var(--text-secondary)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <ArrowLeft size={16} />
          </button>
          <div
            className="flex-shrink-0"
            style={{
              color: viewingFile.type === 'folder' ? '#0071e3' : fileColors[viewingFile.icon || 'file'] || 'var(--text-secondary)',
            }}
          >
            {viewingFile.type === 'folder'
              ? <Folder size={18} strokeWidth={1.5} />
              : (fileIcons[viewingFile.icon || 'file'] || <File size={18} strokeWidth={1.5} />)}
          </div>
          <span className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
            {viewingFile.name}
          </span>
          <span className="ml-auto text-xs flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
            {formatBytes(viewingFile.size)}
          </span>
        </div>
        {/* File content preview */}
        <div className="flex-1 overflow-y-auto p-4">
          <div
            className="rounded-lg border p-4 min-h-[200px]"
            style={{
              backgroundColor: 'var(--bg-surface)',
              borderColor: 'var(--border-subtle)',
            }}
          >
            <div className="flex items-center gap-2 mb-4">
              <ExternalLink size={14} style={{ color: 'var(--text-tertiary)' }} />
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                File preview
              </span>
            </div>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              {viewingFile.name}
            </p>
            <p className="text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
              Size: {formatBytes(viewingFile.size)}
            </p>
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              Modified: {formatDate(viewingFile.modifiedAt)}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full">
      {/* Left sidebar - folder tree (desktop only, hidden on very narrow) */}
      <div
        className="hidden xl:flex w-[200px] flex-shrink-0 flex flex-col overflow-hidden border-r"
        style={{
          backgroundColor: 'var(--bg-sidebar)',
          borderColor: 'var(--border-subtle)',
        }}
      >
        <div
          className="px-3 py-2 text-xs font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-tertiary)' }}
        >
          Folders
        </div>
        <div className="flex-1 overflow-y-auto">
          <AnimatePresence initial={false}>
            {rootFolders.map((folder) => (
              <TreeItem
                key={folder.id}
                folder={folder}
                depth={0}
                isOpen={expandedFolders.has(folder.id)}
                onToggle={() => toggleFolder(folder.id)}
                isSelected={currentFolderId === folder.id}
                onSelect={() => navigateToFolder(folder.id)}
              />
            ))}
          </AnimatePresence>
        </div>

        {/* Bottom stats */}
        <div
          className="px-3 py-2 text-xs border-t"
          style={{
            color: 'var(--text-tertiary)',
            borderColor: 'var(--border-subtle)',
          }}
        >
          <div>{files.filter((f) => f.type === 'file').length} files</div>
          <div>{files.filter((f) => f.type === 'folder').length} folders</div>
        </div>
      </div>

      {/* Right pane - file grid / list */}
      <div
        className="flex-1 flex flex-col overflow-hidden"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        {/* Breadcrumb + search */}
        <div
          className="flex items-center px-2 sm:px-3 py-2 border-b gap-2 flex-shrink-0"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="flex items-center flex-1 min-w-0 overflow-hidden">
            <button
              onClick={() => navigateToFolder(null)}
              className="text-sm transition-colors duration-100 cursor-pointer flex-shrink-0"
              style={{ color: currentFolderId === null ? 'var(--text-primary)' : 'var(--accent-blue)' }}
            >
              Home
            </button>
            {breadcrumb.map((folder, idx) => (
              <React.Fragment key={folder.id}>
                <ChevronRight size={14} className="mx-1 flex-shrink-0" style={{ color: 'var(--text-tertiary)' }} />
                <button
                  onClick={() => navigateToFolder(folder.id)}
                  className="text-sm transition-colors duration-100 truncate cursor-pointer"
                  style={{
                    color: idx === breadcrumb.length - 1 ? 'var(--text-primary)' : 'var(--accent-blue)',
                  }}
                >
                  {folder.name}
                </button>
              </React.Fragment>
            ))}
          </div>
          <div className="relative flex-shrink-0">
            <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-tertiary)' }} />
            <input
              type="text"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="text-sm rounded-md py-1 pl-6 pr-2 w-28 sm:w-32 lg:w-40 transition-all duration-200 focus:w-36 sm:focus:w-48 lg:focus:w-56"
              style={{
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-input)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
        </div>

        {/* File grid */}
        <div
          className="flex-1 overflow-y-auto px-3 py-3"
          onContextMenu={handleContextMenu}
        >
          {currentFiles.length === 0 ? (
            <div
              className="flex flex-col items-center justify-center h-full text-sm"
              style={{ color: 'var(--text-tertiary)' }}
            >
              <FolderOpen size={32} strokeWidth={1} className="mb-2 opacity-30" />
              <p>No files found</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-3 xl:grid-cols-4 gap-2">
              {currentFiles.map((file) => (
                <motion.div
                  key={file.id}
                  layout
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ duration: 0.15 }}
                  onClick={() => {
                    setSelectedFileId(file.id === selectedFileId ? null : file.id);
                    if (file.type === 'folder') {
                      openFolder(file);
                    }
                  }}
                  onDoubleClick={() => {
                    if (file.type === 'folder') {
                      openFolder(file);
                    } else {
                      openFile(file);
                    }
                  }}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setSelectedFileId(file.id);
                    setContextMenu({ x: e.clientX, y: e.clientY });
                  }}
                  className="flex flex-col items-center p-3 rounded-lg cursor-pointer transition-all duration-150 border"
                  style={{
                    backgroundColor:
                      selectedFileId === file.id ? 'rgba(0,113,227,0.08)' : 'var(--bg-surface)',
                    borderColor:
                      selectedFileId === file.id ? 'rgba(0,113,227,0.25)' : 'var(--border-subtle)',
                  }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <div
                    className="mb-2"
                    style={{
                      color: file.type === 'folder' ? '#0071e3' : fileColors[file.icon || 'file'] || 'var(--text-secondary)',
                    }}
                  >
                    {file.type === 'folder'
                      ? <Folder size={32} strokeWidth={1.5} />
                      : (fileIcons[file.icon || 'file'] || <File size={32} strokeWidth={1.5} />)}
                  </div>
                  <div
                    className="text-xs text-center truncate w-full font-medium"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {file.name}
                  </div>
                  {file.size !== undefined && (
                    <div
                      className="text-[10px] mt-0.5"
                      style={{ color: 'var(--text-tertiary)' }}
                    >
                      {formatBytes(file.size)}
                    </div>
                  )}
                  <div
                    className="text-[10px] mt-0.5"
                    style={{ color: 'var(--text-tertiary)' }}
                  >
                    {formatDate(file.modifiedAt)}
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Context menu */}
      <AnimatePresence>
        {contextMenu && (
          <ContextMenu
            x={contextMenu.x}
            y={contextMenu.y}
            onClose={() => setContextMenu(null)}
            onAction={(action) => {
              if (action === 'delete' && selectedFileId) {
                useAppStore.getState().deleteFile(selectedFileId);
                setSelectedFileId(null);
              }
              if (action === 'open' && selectedFileId) {
                const file = files.find((f) => f.id === selectedFileId);
                if (file) {
                  if (file.type === 'folder') {
                    openFolder(file);
                  } else {
                    openFile(file);
                  }
                }
              }
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
