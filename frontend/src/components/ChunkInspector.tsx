import React, { useState, useEffect } from 'react';
import { Search, AlertCircle, Hash } from 'lucide-react';
import type { ApiClient } from '../api/client';
import type { ChunkDetail, DocumentRecord } from '../types';

interface ChunkInspectorProps {
  api: ApiClient;
  selectedDocId: string | null;
}

export const ChunkInspector: React.FC<ChunkInspectorProps> = ({
  api,
  selectedDocId: initialDocId,
}) => {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string>(initialDocId || '');
  const [chunks, setChunks] = useState<ChunkDetail[]>([]);
  const [filename, setFilename] = useState<string>('');
  const [totalChunks, setTotalChunks] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadDocs = async () => {
      try {
        const docs = await api.listDocuments();
        setDocuments(docs);
        if (!selectedId && docs.length > 0) {
          setSelectedId(docs[0].document_id);
        }
      } catch (err: any) {
        setError(err.message || 'Failed to load documents');
      }
    };
    loadDocs();
  }, []);

  useEffect(() => {
    if (initialDocId) {
      setSelectedId(initialDocId);
    }
  }, [initialDocId]);

  useEffect(() => {
    if (!selectedId) return;
    const fetchChunks = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.getDocumentChunks(selectedId);
        setChunks(res.chunks);
        setFilename(res.filename);
        setTotalChunks(res.total_chunks);
      } catch (err: any) {
        setError(err.message || 'Failed to load chunks for this document');
        setChunks([]);
      } finally {
        setLoading(false);
      }
    };
    fetchChunks();
  }, [selectedId]);

  const filteredChunks = chunks.filter((c) =>
    c.content.toLowerCase().includes(filter.toLowerCase())
  );

  const avgChars =
    chunks.length > 0
      ? Math.round(chunks.reduce((acc, c) => acc + c.content.length, 0) / chunks.length)
      : 0;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* Header & Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white">Document Chunk Inspector</h2>
          <p className="text-xs text-slate-400">
            Inspect chunk splitting boundaries, character lengths, and vector metadata.
          </p>
        </div>

        {/* Document Select */}
        <div className="w-full sm:w-72">
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-indigo-500"
          >
            {documents.length === 0 ? (
              <option value="">No documents available</option>
            ) : (
              documents.map((d) => (
                <option key={d.document_id} value={d.document_id}>
                  {d.filename} ({d.chunks} chunks)
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-950/40 border border-red-500/30 text-xs text-red-300">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Metrics Row */}
      {selectedId && !loading && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 text-center">
            <div className="text-xs font-semibold text-slate-400">Total Chunks</div>
            <div className="text-2xl font-bold text-indigo-400 mt-1">{totalChunks}</div>
          </div>
          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 text-center">
            <div className="text-xs font-semibold text-slate-400">Avg Chunk Length</div>
            <div className="text-2xl font-bold text-indigo-400 mt-1">{avgChars} chars</div>
          </div>
          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 text-center">
            <div className="text-xs font-semibold text-slate-400">Active Document</div>
            <div className="text-sm font-semibold text-purple-300 mt-2 truncate">
              {filename || selectedId.slice(0, 12)}
            </div>
          </div>
        </div>
      )}

      {/* Filter */}
      {chunks.length > 0 && (
        <div className="relative w-full">
          <Search className="absolute left-3.5 top-3 h-4 w-4 text-slate-500" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search chunk text by keyword (e.g. leave, stipend, travel)…"
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>
      )}

      {/* Chunks Feed */}
      {loading ? (
        <div className="p-12 text-center text-xs text-slate-400">Retrieving chunk vectors…</div>
      ) : filteredChunks.length === 0 ? (
        <div className="p-12 text-center text-xs text-slate-400">
          No chunks found matching the filter.
        </div>
      ) : (
        <div className="space-y-3">
          {filteredChunks.map((chunk) => (
            <div
              key={chunk.chunk_id}
              className="rounded-2xl bg-slate-900/90 border border-slate-800 p-4 space-y-2 hover:border-slate-700 transition"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-800 text-xs text-slate-400 font-mono">
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 font-bold text-indigo-300 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-500/20">
                    <Hash className="h-3 w-3" /> Chunk #{chunk.chunk_index}
                  </span>
                  <span>{chunk.content.length} chars</span>
                </div>
                <div className="flex items-center gap-2 text-[11px]">
                  {chunk.page && (
                    <span className="bg-slate-800 px-2 py-0.5 rounded text-slate-300">
                      Page {chunk.page}
                    </span>
                  )}
                  <span className="bg-slate-800 px-2 py-0.5 rounded text-slate-400">
                    ID: {chunk.chunk_id}
                  </span>
                </div>
              </div>
              <div className="text-xs text-slate-200 font-mono leading-relaxed whitespace-pre-wrap bg-slate-950/60 p-3 rounded-xl border border-slate-850">
                {chunk.content}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
