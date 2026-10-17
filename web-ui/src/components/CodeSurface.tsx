// CodeSurface — the shared code viewing/editing/running surface.
// One implementation, two presentations: the CodeViewer modal (chat /
// run panel) and the workspace's inline pane. Content comes from the
// real FS API; Python (and other registered languages) get syntax
// highlighting; .py files get a Run button (server-side execution with
// stdout/stderr inline); any file can be edited and saved back.

import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import {
  FileCode2, X, Copy, Check, FolderOpen, Play, Loader2, Pencil, Ban,
} from 'lucide-react';
import hljs from 'highlight.js/lib/core';
import pythonLang from 'highlight.js/lib/languages/python';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import json from 'highlight.js/lib/languages/json';
import bash from 'highlight.js/lib/languages/bash';
import markdown from 'highlight.js/lib/languages/markdown';
import yaml from 'highlight.js/lib/languages/yaml';
import css from 'highlight.js/lib/languages/css';
import xml from 'highlight.js/lib/languages/xml';
import 'highlight.js/styles/github-dark.css';

hljs.registerLanguage('python', pythonLang);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('json', json);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('markdown', markdown);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('css', css);
hljs.registerLanguage('xml', xml);

const EXT_TO_LANG: Record<string, string> = {
  py: 'python',
  js: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'typescript',
  jsx: 'javascript',
  json: 'json',
  sh: 'bash', bash: 'bash',
  md: 'markdown', markdown: 'markdown',
  yml: 'yaml', yaml: 'yaml',
  css: 'css',
  html: 'xml', htm: 'xml', xml: 'xml', svg: 'xml',
};

function languageFor(path: string): string | null {
  const ext = path.split('.').pop()?.toLowerCase() || '';
  return EXT_TO_LANG[ext] || null;
}

interface RunResult {
  ok: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  durationMs: number;
  timedOut: boolean;
  // Deterministic gate (same stages as the agent's runs).
  verification?: {
    run_id?: string;
    verdict: string;
    stages: { name: string; status: string }[];
  };
}

interface CodeSurfaceProps {
  path: string;
  onClose: () => void;
  // Optional "open this file in the workspace view" affordance (modal mode).
  onOpenInWorkspace?: () => void;
}

export function CodeSurface({ path, onClose, onOpenInWorkspace }: CodeSurfaceProps) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<RunResult | null>(null);

  // Streaming run: the server answers {runId} immediately and pushes
  // the output over the WS while the program runs.
  const [liveRunId, setLiveRunId] = useState<string | null>(null);
  const runOutputRef = useRef<HTMLDivElement>(null);
  const liveRun = useAppStore((s) => (liveRunId ? s.liveRuns[liveRunId] : undefined));

  useEffect(() => {
    // Final verdict arrived: the authoritative result replaces the
    // live buffer (full stdout/stderr + gate stages).
    if (liveRun?.done && liveRun.result) {
      setRunResult(liveRun.result as RunResult);
      setRunning(false);
      setLiveRunId(null);
    }
  }, [liveRun?.done, liveRun?.result]);

  useEffect(() => {
    const el = runOutputRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [liveRun?.out, liveRun?.err]);

  // Edit mode: draft + save via the FS write API.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const isPython = path.endsWith('.py');
  const language = languageFor(path);

  useEffect(() => {
    let cancelled = false;
    setContent(null);
    setError(null);
    setRunResult(null);
    setEditing(false);
    setSaveError(null);
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

  const startEditing = () => {
    if (content == null) return;
    setDraft(content);
    setSaveError(null);
    setEditing(true);
  };

  const save = async () => {
    if (saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const r = await fetch('/api/fs/file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, content: draft }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
      setContent(draft);
      setEditing(false);
      setRunResult(null);
    } catch (e: any) {
      setSaveError(String(e.message || e));
    } finally {
      setSaving(false);
    }
  };

  const copy = async () => {
    if (content == null) return;
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  };

  const run = async () => {
    if (running) return;
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
      if (body.runId) {
        // Streaming: output arrives over the WS (fs.run_output events).
        setLiveRunId(body.runId);
      } else {
        // Legacy/short path: the full result in one response.
        setRunResult(body as RunResult);
        setRunning(false);
      }
    } catch (e: any) {
      setRunResult({
        ok: false, exitCode: -1, stdout: '',
        stderr: String(e.message || e), durationMs: 0, timedOut: false,
      });
      setRunning(false);
    }
  };

  const lines = content != null ? content.split('\n').length : 0;
  const highlighted =
    content != null && language
      ? hljs.highlight(content, { language, ignoreIllegals: true }).value
      : null;

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
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
        {editing ? (
          <>
            <button
              onClick={save}
              disabled={saving}
              className="flex items-center gap-1 px-2 py-1 rounded-md cursor-pointer flex-shrink-0 text-[11.5px]"
              style={{
                backgroundColor: 'var(--accent-blue)',
                color: '#ffffff',
                opacity: saving ? 0.6 : 1,
              }}
              title="Save (Ctrl/Cmd+S)"
            >
              {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Save
            </button>
            <button
              onClick={() => setEditing(false)}
              className="flex items-center gap-1 px-2 py-1 rounded-md cursor-pointer flex-shrink-0 text-[11.5px]"
              style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
              title="Cancel"
            >
              <Ban size={11} /> Cancel
            </button>
          </>
        ) : (
          <>
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
              onClick={startEditing}
              disabled={content == null}
              className="p-1.5 rounded-md cursor-pointer flex-shrink-0"
              style={{ color: 'var(--text-tertiary)' }}
              title="Edit"
            >
              <Pencil size={13} />
            </button>
          </>
        )}
        <button
          onClick={copy}
          className="p-1.5 rounded-md cursor-pointer flex-shrink-0"
          style={{ color: copied ? 'var(--success, #34c759)' : 'var(--text-tertiary)' }}
          title="Copy"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </button>
        {onOpenInWorkspace && (
          <button
            onClick={onOpenInWorkspace}
            className="flex items-center gap-1 px-2 py-1 rounded-md cursor-pointer flex-shrink-0 text-[11.5px]"
            style={{ color: 'var(--accent-blue)', border: '1px solid var(--border-subtle)' }}
            title="Open in workspace"
          >
            <FolderOpen size={12} /> Workspace
          </button>
        )}
        <button
          onClick={onClose}
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
        ) : editing ? (
          <div className="flex flex-col h-full min-h-[300px]">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === 's') {
                  e.preventDefault();
                  save();
                }
              }}
              spellCheck={false}
              className="flex-1 w-full px-4 py-3 text-[12px] leading-relaxed bg-transparent border-none outline-none resize-none"
              style={{
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono, monospace)',
              }}
            />
            {saveError && (
              <p
                className="px-4 py-1.5 text-[11.5px] border-t flex-shrink-0"
                style={{
                  color: 'var(--warning, #ff9500)',
                  borderColor: 'var(--border-subtle)',
                }}
              >
                {saveError}
              </p>
            )}
          </div>
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
        {(runResult || (running && liveRun && (liveRun.out || liveRun.err))) && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex-shrink-0 overflow-hidden border-t"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div ref={runOutputRef} className="px-3 py-2 max-h-[220px] overflow-auto">
              {running && liveRun ? (
                <>
                  <div
                    className="flex items-center gap-2 text-[11px] mb-1"
                    style={{ color: 'var(--text-tertiary)' }}
                  >
                    running…
                  </div>
                  {liveRun.out && (
                    <pre
                      className="text-[11.5px] whitespace-pre-wrap"
                      style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono, monospace)' }}
                    >
                      {liveRun.out}
                    </pre>
                  )}
                  {liveRun.err && (
                    <pre
                      className="text-[11.5px] whitespace-pre-wrap"
                      style={{ color: 'var(--warning, #ff9500)', fontFamily: 'var(--font-mono, monospace)' }}
                    >
                      {liveRun.err}
                    </pre>
                  )}
                </>
              ) : runResult && (
              <>
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
              {runResult.verification && (
                <div className="flex items-center gap-1.5 flex-wrap mt-1">
                  <span
                    className="text-[10.5px]"
                    style={{
                      color: runResult.verification.verdict === 'passed'
                        ? 'var(--success, #34c759)'
                        : runResult.verification.verdict === 'failed'
                          ? 'var(--warning, #ff9500)'
                          : 'var(--text-tertiary)',
                    }}
                  >
                    {runResult.verification.verdict}
                  </span>
                  {runResult.verification.stages.map((stage) => {
                    const color =
                      stage.status === 'passed' ? 'var(--success, #34c759)'
                      : stage.status === 'failed' || stage.status === 'inconclusive'
                        ? 'var(--warning, #ff9500)'
                        : 'var(--text-tertiary)';
                    return (
                      <span
                        key={stage.name}
                        className="flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10.5px]"
                        style={{ color, border: `1px solid ${color}` }}
                        title={`stage ${stage.name}: ${stage.status}`}
                      >
                        <span
                          aria-hidden
                          className="w-1.5 h-1.5 rounded-full"
                          style={{ backgroundColor: color }}
                        />
                        {stage.name}
                      </span>
                    );
                  })}
                </div>
              )}
              </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
