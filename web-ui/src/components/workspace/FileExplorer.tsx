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
} from 'lucide-react';
import { CodeSurface } from '../CodeSurface';

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
  const [viewingPath, setViewingPath] = useState<string | null>(null);
  const [openPaths, setOpenPaths] = useState<string[]>([]);
  const [explorerWidth, setExplorerWidth] = useState(36);
  const rootRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const currentProject = useAppStore((s) => s.currentProject);
  const setCurrentProject = useAppStore((s) => s.setCurrentProject);
  const pendingOpenFile = useAppStore((s) => s.pendingOpenFile);
  const setPendingOpenFile = useAppStore((s) => s.setPendingOpenFile);
  const refreshRef = useRef<((path?: string) => Promise<void>) | null>(null);

  // Open a file requested from elsewhere (e.g. the code viewer's
  // "Workspace" button): show it in the inline CodeSurface.
  useEffect(() => {
    if (pendingOpenFile) {
      const parent = pendingOpenFile.includes('/') ? pendingOpenFile.slice(0, pendingOpenFile.lastIndexOf('/')) : '';
      refreshRef.current?.(parent);
      setViewingPath(pendingOpenFile);
      setOpenPaths((paths) => paths.includes(pendingOpenFile) ? paths : [...paths, pendingOpenFile]);
    }
    if (pendingOpenFile) setPendingOpenFile(null);
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

  const handleRename = async (entry: FsEntry) => {
    const newName = prompt('Rename to', entry.name);
    if (!newName || newName === entry.name) return;
    try {
      await rename(entry.path, newName);
    } catch (e: any) {
      setError(e.message);
      return;
    }
    // Keep the open viewer pointing at the file that still exists.
    const newPath = dir ? `${dir}/${newName}` : newName;
    setOpenPaths((paths) => paths.map((path) =>
      path === entry.path ? newPath :
      path.startsWith(entry.path + "/") ? newPath + path.slice(entry.path.length) : path));
    if (viewingPath === entry.path) setViewingPath(newPath);
    else if (viewingPath && viewingPath.startsWith(entry.path + '/')) {
      setViewingPath(newPath + viewingPath.slice(entry.path.length));
    }
    await refresh(dir);
  };

  const handleDelete = async (entry: FsEntry) => {
    const label = entry.type === 'folder' ? 'folder and ALL its contents' : 'file';
    if (!confirm(`Delete ${label} "${entry.name}"?`)) return;
    try {
      await deleteEntry(entry.path);
    } catch (e: any) {
      setError(e.message);
      return;
    }
    // The open viewer must not outlive the file it shows.
    const deletedTabs = openPaths.filter((path) =>
      path === entry.path || path.startsWith(entry.path + "/"));
    setOpenPaths((paths) => paths.filter((path) => !deletedTabs.includes(path)));
    if (viewingPath && deletedTabs.includes(viewingPath)) {
      setViewingPath(openPaths.find((path) => !deletedTabs.includes(path)) || null);
    }
    await refresh(dir);
  };

  const openFile = (entry: FsEntry) => {
    setError(null);
    setViewingPath(entry.path);
    setOpenPaths((paths) => paths.includes(entry.path) ? paths : [...paths, entry.path]);
  };

  const closeTab = (path: string) => {
    const index = openPaths.indexOf(path);
    const remaining = openPaths.filter((item) => item !== path);
    setOpenPaths(remaining);
    if (viewingPath === path) {
      setViewingPath(remaining[Math.min(index, remaining.length - 1)] || null);
    }
  };

  const startResize = (event: React.PointerEvent) => {
    event.preventDefault();
    const move = (moveEvent: PointerEvent) => {
      const bounds = rootRef.current?.getBoundingClientRect();
      if (!bounds) return;
      const percent = ((moveEvent.clientX - bounds.left) / bounds.width) * 100;
      setExplorerWidth(Math.min(65, Math.max(22, percent)));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  return (
    <div ref={rootRef} className="relative flex h-full min-h-0">
      {/* Explorer column (files, breadcrumbs, project selector).
          Full width until a file is open on desktop — a fixed 340px
          column next to empty space looked broken. */}
      <div
        className={'flex flex-col h-full min-w-0 flex-1 ' + (viewingPath ? 'lg:flex-none' : '')}
        style={{ borderColor: "var(--border-subtle)", width: viewingPath ? explorerWidth + "%" : undefined }}
      >
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
        <strong style={{ color: 'var(--text-secondary)' }}>{currentProject || 'Workspace'}</strong>
        <span>{dir || 'project root'}</span>
        <span>{entries.filter((e) => e.type === 'file').length} files</span>
        <span>{entries.filter((e) => e.type === 'folder').length} folders</span>
      </div>
      </div>

      {viewingPath && (
        <div className="hidden lg:block w-1 cursor-col-resize flex-shrink-0"
          style={{ backgroundColor: "var(--border-subtle)" }} onPointerDown={startResize}
          role="separator" aria-orientation="vertical" aria-label="Resize project explorer" />
      )}

      {/* Desktop: inline code surface (highlight, run, edit) next to the
          list — same surface as the chat's CodeViewer modal, presented
          as a floating card. */}
      {viewingPath && (
        <div className="hidden lg:flex flex-1 min-w-0 p-3">
          <div
            className="flex flex-col flex-1 min-h-0 rounded-xl overflow-hidden"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
          >
            <div className="flex h-9 overflow-x-auto border-b" style={{ borderColor: "var(--border-subtle)" }}>
              {openPaths.map((path) => (
                <button key={path} onClick={() => setViewingPath(path)}
                  className="flex items-center gap-2 px-3 text-[11px] border-r flex-shrink-0"
                  style={{ color: path === viewingPath ? "var(--accent-blue)" : "var(--text-secondary)", borderColor: "var(--border-subtle)", backgroundColor: path === viewingPath ? "var(--bg-primary)" : "transparent" }}>
                  <span>{path.split("/").pop()}</span>
                  <span onClick={(event) => { event.stopPropagation(); closeTab(path); }} aria-label={"Close " + path}>×</span>
                </button>
              ))}
            </div>
            <div className="flex-1 min-h-0"><CodeSurface path={viewingPath} onClose={() => closeTab(viewingPath)} /></div>
          </div>
        </div>
      )}

      {/* Mobile: full-cover code surface */}
      <AnimatePresence>
        {viewingPath && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="lg:hidden absolute inset-0 z-20 flex flex-col"
            style={{ backgroundColor: 'var(--bg-primary)' }}
          >
            <CodeSurface path={viewingPath} onClose={() => setViewingPath(null)} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
