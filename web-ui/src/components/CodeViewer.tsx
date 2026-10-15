// CodeViewer — in-chat viewer for files the agent wrote. Opens from the
// run panel's file list; content comes from the real FS API. Python
// files get syntax highlighting (highlight.js, python only) and a Run
// button that executes the file server-side (/api/fs/run) and shows
// stdout/stderr inline — the code surface is now read + run.

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FileCode2, X, Copy, Check, FolderOpen, Play, Loader2 } from 'lucide-react';
import hljs from 'highlight.js/lib/core';
import pythonLang from 'highlight.js/lib/languages/python';
import 'highlight.js/styles/github-dark.css';
import { useAppStore } from '@/store/appStore';

hljs.registerLanguage('python', pythonLang);

interface RunResult {
  ok: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
}

export function CodeViewer() {
  const path = useAppStore((s) => s.viewerFilePath);
  const closeFileViewer = useAppStore((s) => s.closeFileViewer);
  const setView = useAppStore((s) => s.setView);
  const setPendingOpenFile = useAppStore((s) => s.setPendingOpenFile);

  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<RunResult | null>(null);

  const isPython = !!path && path.endsWith('.py');

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setContent(null);
    setError(null);
    setRunResult(null);
    fetch(`/api/fs/file?path=${encodeURIComponent(path)}`)
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
        return body;
      })
      .then((data) => {
        if (!cancelled) setContent(data.binary ? '(binary file)' : data.content);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e.message || e));
      });
    return () => { cancelled = true; };
  }, [path]);

  const copy = async () => {
    if (content == null) return;
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  };

  const run = async () => {
    if (!path || running) return;
    setRunning(true);
    setRunResult(null);
    try {
      const r = await fetch('/api/fs/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
      setRunResult(body as RunResult);
    } catch (e: any) {
      setRunResult({
        ok: false, exitCode: -1, stdout: '',
        stderr: String(e.message || e), durationMs: 0, timedOut: false,
      });
    } finally {
      setRunning(false);
    }
  };

  const openInWorkspace = () => {
    if (!path) return;
    setPendingOpenFile(path);
    setView('workspace');
    closeFileViewer();
  };

  const lines = content != null ? content.split('\n').length : 0;
  const highlighted =
    content != null && isPython
      ? hljs.highlight(content, { language: 'python', ignoreIllegals: true }).value
      : null;

  return (
    <AnimatePresence>
      {path && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ backgroundColor: 'rgba(0, 0, 0, 0.55)' }}
          onClick={closeFileViewer}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0, 0, 0.2, 1] }}
            className="w-full max-w-[860px] max-h-[80vh] flex flex-col rounded-xl overflow-hidden"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div
              className="flex items-center gap-2 px-3 h-11 flex-shrink-0 border-b"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <FileCode2 size={14} style={{ color: 'var(--accent-blue)' }} />
              <span className="text-[12.5px] font-medium truncate flex-1 min-w-0" style={{ color: 'var(--text-primary)' }}>
                {path}
              </span>
              {content != null && (
                <span className="text-[11px] flex-shrink-0" style={{ color: 'var(--text-tertiary)' }}>
                  {lines} lines
                </span>
              )}
              {isPython && (
                <button
                  onClick={run}
                  disabled={running || content == null}
                  className="flex items-center gap-1 px-2 py-1 rounded-md cursor-pointer flex-shrink-0 text-[11.5px]"
                  style={{
                    backgroundColor: 'var(--accent-blue)',
                    color: '#ffffff',
                    opacity: running || content == null ? 0.6 : 1,
                  }}
                  title="Run this file"
                >
                  {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} Run
                </button>
              )}
              <button
                onClick={copy}
                className="p-1.5 rounded-md cursor-pointer flex-shrink-0"
                style={{ color: copied ? 'var(--success, #34c759)' : 'var(--text-tertiary)' }}
                title="Copy"
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
              </button>
              <button
                onClick={openInWorkspace}
                className="flex items-center gap-1 px-2 py-1 rounded-md cursor-pointer flex-shrink-0 text-[11.5px]"
                style={{ color: 'var(--accent-blue)', border: '1px solid var(--border-subtle)' }}
                title="Open in workspace"
              >
                <FolderOpen size={12} /> Workspace
              </button>
              <button
                onClick={closeFileViewer}
                className="p-1.5 rounded-md cursor-pointer flex-shrink-0"
                style={{ color: 'var(--text-tertiary)' }}
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-auto min-h-0">
              {error ? (
                <p className="px-4 py-6 text-[12.5px]" style={{ color: 'var(--warning, #ff9500)' }}>
                  {error}
                </p>
              ) : content == null ? (
                <p className="px-4 py-6 text-[12.5px]" style={{ color: 'var(--text-tertiary)' }}>
                  Loading…
                </p>
              ) : (
                <pre
                  className="px-4 py-3 text-[12px] leading-relaxed whitespace-pre hljs"
                  style={{
                    backgroundColor: 'transparent',
                    fontFamily: 'var(--font-mono, monospace)',
                  }}
                >
                  {highlighted != null ? (
                    <code dangerouslySetInnerHTML={{ __html: highlighted }} />
                  ) : (
                    content
                  )}
                </pre>
              )}
            </div>

            {/* Run output */}
            <AnimatePresence>
              {runResult && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="flex-shrink-0 overflow-hidden border-t"
                  style={{ borderColor: 'var(--border-subtle)' }}
                >
                  <div className="px-3 py-2 max-h-[220px] overflow-auto">
                    <div
                      className="flex items-center gap-2 text-[11px] mb-1"
                      style={{ color: runResult.ok ? 'var(--success, #34c759)' : 'var(--warning, #ff9500)' }}
                    >
                      {runResult.ok ? 'exit 0' : `exit ${runResult.exitCode}`}
                      <span style={{ color: 'var(--text-tertiary)' }}>
                        {runResult.durationMs} ms{runResult.timedOut ? ' — timed out' : ''}
                      </span>
                    </div>
                    {runResult.stdout && (
                      <pre
                        className="text-[11.5px] whitespace-pre-wrap"
                        style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono, monospace)' }}
                      >
                        {runResult.stdout}
                      </pre>
                    )}
                    {runResult.stderr && (
                      <pre
                        className="text-[11.5px] whitespace-pre-wrap"
                        style={{ color: 'var(--warning, #ff9500)', fontFamily: 'var(--font-mono, monospace)' }}
                      >
                        {runResult.stderr}
                      </pre>
                    )}
                    {!runResult.stdout && !runResult.stderr && (
                      <p className="text-[11.5px]" style={{ color: 'var(--text-tertiary)' }}>
                        (no output)
                      </p>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
