import React, { useState } from 'react';
import {
  X,
  FileText,
  Copy,
  Check,
  Search,
  ExternalLink,
  ShieldCheck,
  Bookmark,
} from 'lucide-react';
import type { Source } from '../types';

interface CitationDrawerProps {
  source: Source | null;
  searchQuery: string;
  isOpen: boolean;
  onClose: () => void;
  onInspectDocument?: (filename: string) => void;
}

export const CitationDrawer: React.FC<CitationDrawerProps> = ({
  source,
  searchQuery,
  isOpen,
  onClose,
  onInspectDocument,
}) => {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !source) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(source.excerpt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const relevancePct = Math.min(100, Math.round((source.relevance_score ?? 0.8) * 100));

  // Keyword highlighting function
  const highlightExcerpt = (text: string, query: string) => {
    if (!query.trim()) return <span>{text}</span>;

    // Filter out common short stopwords
    const words = query
      .toLowerCase()
      .split(/\s+/)
      .map((w) => w.replace(/[^\w]/g, ''))
      .filter((w) => w.length > 2);

    if (words.length === 0) return <span>{text}</span>;

    const regex = new RegExp(`(${words.join('|')})`, 'gi');
    const parts = text.split(regex);

    return (
      <>
        {parts.map((part, i) =>
          words.includes(part.toLowerCase()) ? (
            <mark
              key={i}
              className="bg-indigo-500/30 text-indigo-200 px-1 py-0.5 rounded font-semibold border border-indigo-500/40"
            >
              {part}
            </mark>
          ) : (
            <span key={i}>{part}</span>
          )
        )}
      </>
    );
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="absolute inset-0 bg-slate-950/70 backdrop-blur-xs transition-opacity duration-300"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col transform transition-transform duration-300 ease-in-out">
          {/* Header */}
          <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
                <Bookmark className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Citation Inspector</h3>
                <p className="text-[11px] text-slate-400">Verified document ground truth</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {/* File Info Card */}
            <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-100 break-all">
                  <FileText className="h-4 w-4 text-indigo-400 shrink-0" />
                  <span>{source.filename}</span>
                </div>
                {source.relevance_score !== undefined && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[11px] font-bold shrink-0 border ${
                      relevancePct >= 85
                        ? 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40'
                        : relevancePct >= 70
                        ? 'bg-indigo-950/60 text-indigo-300 border-indigo-500/40'
                        : 'bg-amber-950/60 text-amber-300 border-amber-500/40'
                    }`}
                  >
                    {relevancePct}% Match
                  </span>
                )}
              </div>

              {/* Relevance Meter */}
              <div>
                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                  <span>Relevance Score</span>
                  <span className="font-mono text-slate-300">{source.relevance_score?.toFixed(4)}</span>
                </div>
                <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      relevancePct >= 85 ? 'bg-emerald-500' : relevancePct >= 70 ? 'bg-indigo-500' : 'bg-amber-500'
                    }`}
                    style={{ width: `${relevancePct}%` }}
                  />
                </div>
              </div>

              {/* Metadata Badges */}
              <div className="flex flex-wrap gap-2 pt-1 text-xs">
                {source.page && (
                  <div className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700/80 text-slate-300">
                    <span className="text-slate-500 mr-1.5">Page</span>
                    <span className="font-semibold text-white">{source.page}</span>
                  </div>
                )}
                {source.chunk_index !== undefined && (
                  <div className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700/80 text-slate-300">
                    <span className="text-slate-500 mr-1.5">Chunk ID</span>
                    <span className="font-mono font-semibold text-white">#{source.chunk_index}</span>
                  </div>
                )}
                <div className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-950/40 border border-indigo-500/30 text-indigo-300 text-xs">
                  <ShieldCheck className="h-3 w-3" /> Grounded Context
                </div>
              </div>
            </div>

            {/* Cited Excerpt */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                <span className="flex items-center gap-1.5">
                  <Search className="h-3.5 w-3.5 text-indigo-400" />
                  Extracted Passage Content
                </span>
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 transition"
                >
                  {copied ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-400" />
                      <span className="text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      <span>Copy Excerpt</span>
                    </>
                  )}
                </button>
              </div>

              <div className="p-4 rounded-xl bg-slate-950 border border-indigo-500/20 text-xs sm:text-sm text-slate-200 leading-relaxed font-sans whitespace-pre-wrap selection:bg-indigo-500/30">
                {highlightExcerpt(source.excerpt, searchQuery)}
              </div>
              <p className="text-[11px] text-slate-500 italic">
                * Matching query keywords are automatically highlighted above.
              </p>
            </div>
          </div>

          {/* Footer Actions */}
          <div className="p-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between gap-3">
            {onInspectDocument && (
              <button
                onClick={() => {
                  onInspectDocument(source.filename);
                  onClose();
                }}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-semibold transition border border-slate-700"
              >
                <ExternalLink className="h-3.5 w-3.5 text-indigo-400" />
                Inspect Chunks
              </button>
            )}
            <button
              onClick={handleCopy}
              className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/30 transition"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? 'Copied to Clipboard' : 'Copy Full Passage'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
