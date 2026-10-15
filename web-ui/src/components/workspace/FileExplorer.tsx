// FileExplorer — real workspace files via the BigBrain FS API
// (GET/POST/DELETE /api/fs/*). Replaces the original mock tree: listing,
// navigation, reading, creating, renaming and deleting are actual
// filesystem operations inside the server's workspace root. The agent
// (PythonBrain) writes into the same root, so agent-created files show up
// here on refresh.

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAppStore } from '@/store/appStore';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Folder,
  FileText,
  Code2,
  Image as ImageIcon,
  File as FileIcon,
  ChevronRight,
  Home,
  Trash2,
  FolderPlus,
  FilePlus2,
  Pencil,
  RefreshCw,
  X,
} from 'lucide-react';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

interface Project {
  name: string;
  path: string;
  created: number | null;
}

interface FsEntry {
  name: string;
  path: string;
  type: 'folder' | 'file';
  size: number | null;
  modified: number;
  extension: string | null;
}

async function fsApi<T>(path: string, opts?: RequestInit): Promise<T> {
  const response = await fetch(path, opts);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error((body as any).error || `HTTP ${response.status}`);
  return body as T;
}

const listDir = (path: string) =>
  fsApi<{ path: string; entries: FsEntry[] }>(
    `/api/fs/list?path=${encodeURIComponent(path)}`
  );

const readFile = (path: string) =>
  fsApi<{ content: string; binary: boolean; truncated: boolean }>(
    `/api/fs/file?path=${encodeURIComponent(path)}`
  );

const writeFile = (path: string, content: string) =>
  fsApi<{ ok: boolean }>(`/api/fs/file`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content }),
  });

const mkdir = (path: string) =>
  fsApi<{ ok: boolean }>(`/api/fs/mkdir`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });

const rename = (path: string, newName: string) =>
  fsApi<{ ok: boolean }>(`/api/fs/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, newName }),
  });

const deleteEntry = (path: string) =>
  fsApi<{ ok: boolean }>(`/api/fs/file?path=${encodeURIComponent(path)}`, {
    method: 'DELETE',
  });

const listProjects = () => fsApi<{ projects: Project[] }>(`/api/fs/projects`);

const createProject = (name: string) =>
  fsApi<{ ok: boolean }>(`/api/fs/project`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });

function iconFor(entry: FsEntry, size = 15) {
  if (entry.type === 'folder') return <Folder size={size} strokeWidth={1.5} />;
  const ext = (entry.extension || '').toLowerCase();
  if (['ts', 'tsx', 'js', 'mjs', 'py', 'json', 'css', 'html'].includes(ext))
    return <Code2 size={size} strokeWidth={1.5} />;
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext))
    return <ImageIcon size={size} strokeWidth={1.5} />;
  if (['md', 'txt', 'log'].includes(ext))
    return <FileText size={size} strokeWidth={1.5} />;
  return <FileIcon size={size} strokeWidth={1.5} />;
}

function formatSize(bytes: number | null): string {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function FileExplorer() {
  const [dir, setDir] = useState('');
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewing, setViewing] = useState<{ path: string; content: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const currentProject = useAppStore((s) => s.currentProject);
  const setCurrentProject = useAppStore((s) => s.setCurrentProject);
  const pendingOpenFile = useAppStore((s) => s.pendingOpenFile);
  const setPendingOpenFile = useAppStore((s) => s.setPendingOpenFile);
  const refreshRef = useRef<((path?: string) => Promise<void>) | null>(null);

  // Open a file requested from elsewhere (e.g. the run panel's file list):
  // read it and show the viewer overlay.
  useEffect(() => {
    if (!pendingOpenFile) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await readFile(pendingOpenFile);
        if (!cancelled) setViewing({ path: pendingOpenFile, content: data.content });
      } catch (e: any) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setPendingOpenFile(null);
      }
    })();
    return () => { cancelled = true; };
  }, [pendingOpenFile, setPendingOpenFile]);

  // Agent writes (workspace.file_written events) auto-refresh the listing.
  const lastWrite = useAppStore((s) => {
    const writes = s.agentActivities.filter((a) => a.type === 'workspace.file_written');
    return writes.length ? writes[writes.length - 1].ts : 0;
  });
  useEffect(() => {
    if (lastWrite > 0) refreshRef.current?.();
  }, [lastWrite]);

  const refresh = useCallback(async (path = dir) => {
    setLoading(true);
    setError(null);
    try {
      const result = await listDir(path);
      setEntries(result.entries);
      setDir(path);
      if (!path) {
        try {
          const pr = await listProjects();
          setProjects(pr.projects || []);
          const cur = await fsApi<{ project: string | null }>(`/api/fs/current-project`);
          setCurrentProject(cur.project);
        } catch (e) {
          setProjects([]);
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [dir]);

  useEffect(() => {
    refresh('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the ref current so the write watcher uses the latest closure.
  useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  const crumbs = dir ? dir.split('/') : [];

  const guard = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh(dir);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleNewProject = () => {
    const name = prompt('New project name');
    if (!name) return;
    guard(() => createProject(name));
  };

  const handleNewFolder = () => {
    const name = prompt('New folder name');
    if (!name) return;
    guard(() => mkdir(dir ? `${dir}/${name}` : name));
  };

  const handleNewFile = () => {
    const name = prompt('New file name (e.g. notes.md)');
    if (!name) return;
    guard(() => writeFile(dir ? `${dir}/${name}` : name, ''));
  };

  const handleRename = (entry: FsEntry) => {
    const newName = prompt('Rename to', entry.name);
    if (!newName || newName === entry.name) return;
    guard(() => rename(entry.path, newName));
  };

  const handleDelete = (entry: FsEntry) => {
    const label = entry.type === 'folder' ? 'folder and ALL its contents' : 'file';
    if (!confirm(`Delete ${label} "${entry.name}"?`)) return;
    guard(() => deleteEntry(entry.path));
  };

  const openFile = async (entry: FsEntry) => {
    setError(null);
    try {
      const data = await readFile(entry.path);
      setViewing({ path: entry.path, content: data.content });
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Header: breadcrumbs + actions */}
      <div className="flex items-center gap-1.5 px-3 h-11 flex-shrink-0 border-b"
           style={{ borderColor: 'var(--border-subtle)' }}>
        <button
          onClick={() => refresh('')}
          className="p-1.5 rounded-md cursor-pointer"
          style={{ color: 'var(--text-tertiary)' }}
          aria-label="Root"
        >
          <Home size={14} />
        </button>
        {crumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1.5">
            <ChevronRight size={11} style={{ color: 'var(--text-tertiary)' }} />
            <button
              onClick={() => refresh(crumbs.slice(0, i + 1).join('/'))}
              className="text-[12px] cursor-pointer"
              style={{ color: 'var(--text-secondary)' }}
            >
              {crumb}
            </button>
          </span>
        ))}
        {/* Working-project selector (agent writes + chat context) */}
        <select
          value={currentProject || ''}
          onChange={async (e) => {
            const value = e.target.value || null;
            try {
              await fsApi(`/api/fs/current-project`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project: value }),
              });
              setCurrentProject(value);
              refresh(dir);
            } catch (err: any) {
              setError(err.message);
            }
          }}
          className="mr-1.5 px-2 py-1 rounded-md text-[11.5px] outline-none cursor-pointer"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            color: currentProject ? 'var(--accent-blue)' : 'var(--text-tertiary)',
            maxWidth: 110,
          }}
          title="Working project"
        >
          <option value="">Global</option>
          {projects.map((p) => (
            <option key={p.path} value={p.path}>{p.name}</option>
          ))}
        </select>
        <div className="flex items-center gap-0.5">
          <button onClick={handleNewProject} disabled={busy} title="New project"
                  className="p-1.5 rounded-md cursor-pointer"
                  style={{ color: 'var(--text-tertiary)' }}>
            <FolderPlus size={14} style={{ color: 'var(--accent-blue)' }} />
          </button>
          <button onClick={handleNewFolder} disabled={busy} title="New folder"
                  className="p-1.5 rounded-md cursor-pointer"
                  style={{ color: 'var(--text-tertiary)' }}>
            <FolderPlus size={14} />
          </button>
          <button onClick={handleNewFile} disabled={busy} title="New file"
                  className="p-1.5 rounded-md cursor-pointer"
                  style={{ color: 'var(--text-tertiary)' }}>
            <FilePlus2 size={14} />
          </button>
          <button onClick={() => refresh(dir)} disabled={busy} title="Refresh"
                  className="p-1.5 rounded-md cursor-pointer"
                  style={{ color: 'var(--text-tertiary)' }}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Error line */}
      {error && (
        <div className="px-3 py-1.5 text-[11px]" style={{ color: 'var(--warning, #ff9500)' }}>
          {error}
        </div>
      )}

      {/* Entries */}
      <div className="flex-1 overflow-y-auto px-2 py-1.5 min-h-0">
        {entries.length === 0 && !loading && (
          <p className="text-xs text-center py-8" style={{ color: 'var(--text-tertiary)' }}>
            Empty folder
          </p>
        )}
        <AnimatePresence initial={false}>
          {entries.map((entry) => (
            <motion.div
              key={entry.path}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, ease: easeOut }}
              className="group flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer"
              style={{ color: 'var(--text-primary)' }}
              onClick={() =>
                entry.type === 'folder' ? refresh(entry.path) : openFile(entry)
              }
            >
              <span className="flex-shrink-0" style={{ color: 'var(--text-secondary)' }}>
                {iconFor(entry)}
              </span>
              <span className="text-[13px] truncate flex-1 min-w-0">{entry.name}</span>
              {!dir && projects.some((p) => p.path === entry.name) && (
                <span
                  className="text-[9.5px] uppercase tracking-wide px-1.5 py-0.5 rounded-full flex-shrink-0"
                  style={{
                    color: 'var(--accent-blue)',
                    border: '1px solid var(--accent-blue)',
                    opacity: 0.8,
                  }}
                >
                  project
                </span>
              )}
              <span className="text-[10.5px] flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                {formatSize(entry.size)}
              </span>
              <span
                className="flex-shrink-0 hidden group-hover:flex items-center gap-0.5"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => handleRename(entry)}
                  title="Rename"
                  className="p-1 rounded-md cursor-pointer"
                  style={{ color: 'var(--text-tertiary)' }}
                >
                  <Pencil size={12} />
                </button>
                <button
                  onClick={() => handleDelete(entry)}
                  title="Delete"
                  className="p-1 rounded-md cursor-pointer"
                  style={{ color: 'var(--text-tertiary)' }}
                >
                  <Trash2 size={12} />
                </button>
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Footer count */}
      <div className="flex items-center gap-3 px-3 h-8 flex-shrink-0 border-t text-[11px]"
           style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-tertiary)' }}>
        <span>{entries.filter((e) => e.type === 'file').length} files</span>
        <span>{entries.filter((e) => e.type === 'folder').length} folders</span>
      </div>

      {/* File viewer overlay */}
      <AnimatePresence>
        {viewing && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 z-20 flex flex-col"
            style={{ backgroundColor: 'var(--bg-primary)' }}
          >
            <div className="flex items-center gap-2 px-3 h-11 border-b flex-shrink-0"
                 style={{ borderColor: 'var(--border-subtle)' }}>
              <FileText size={14} style={{ color: 'var(--text-tertiary)' }} />
              <span className="text-[12.5px] font-medium truncate"
                    style={{ color: 'var(--text-primary)' }}>
                {viewing.path}
              </span>
              <button
                onClick={() => setViewing(null)}
                className="ml-auto p-1.5 rounded-md cursor-pointer"
                style={{ color: 'var(--text-tertiary)' }}
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>
            <pre
              className="flex-1 overflow-auto px-4 py-3 text-[12px] whitespace-pre-wrap"
              style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono, monospace)' }}
            >
              {viewing.content}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
