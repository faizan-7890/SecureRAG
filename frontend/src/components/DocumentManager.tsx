import React, { useState, useEffect, useRef } from 'react';
import {
  Upload,
  FileText,
  Trash2,
  Search,
  CheckCircle2,
  AlertCircle,
  FileCode,
  FileSpreadsheet,
  FileQuestion,
} from 'lucide-react';
import type { ApiClient } from '../api/client';
import type { DocumentRecord } from '../types';

interface DocumentManagerProps {
  api: ApiClient;
  onInspectDocument: (documentId: string) => void;
}

export const DocumentManager: React.FC<DocumentManagerProps> = ({
  api,
  onInspectDocument,
}) => {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocuments = async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await api.listDocuments();
      setDocuments(docs);
    } catch (err: any) {
      setError(err.message || 'Failed to load documents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const handleFileUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setError(null);
    setSuccess(null);

    let count = 0;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        await api.uploadDocument(file);
        count++;
      } catch (err: any) {
        setError(`Failed to ingest ${file.name}: ${err.message}`);
      }
    }

    if (count > 0) {
      setSuccess(`Successfully ingested ${count} document(s).`);
      loadDocuments();
    }
    setUploading(false);
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!confirm(`Are you sure you want to delete ${filename}?`)) return;
    try {
      await api.deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.document_id !== docId));
      setSuccess(`Deleted ${filename}`);
    } catch (err: any) {
      setError(err.message || 'Failed to delete document');
    }
  };

  const filteredDocs = documents.filter((doc) =>
    doc.filename.toLowerCase().includes(filter.toLowerCase())
  );

  const getFileIcon = (ext: string) => {
    if (ext === '.pdf') return <FileText className="h-5 w-5 text-red-400" />;
    if (ext === '.md' || ext === '.markdown') return <FileCode className="h-5 w-5 text-indigo-400" />;
    if (ext === '.txt') return <FileSpreadsheet className="h-5 w-5 text-blue-400" />;
    return <FileQuestion className="h-5 w-5 text-slate-400" />;
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white">Document Repository</h2>
          <p className="text-xs text-slate-400">
            Upload, chunk, and index private knowledge with multi-tenant RBAC policies.
          </p>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-950/40 border border-red-500/30 text-xs text-red-300">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30 text-xs text-emerald-300">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {/* Dropzone Upload */}
      <div
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleFileUpload(e.dataTransfer.files);
        }}
        className="flex flex-col items-center justify-center p-8 rounded-2xl border-2 border-dashed border-slate-800 hover:border-indigo-500/50 bg-slate-900/40 hover:bg-slate-900/80 transition cursor-pointer text-center group"
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.md,.markdown"
          onChange={(e) => handleFileUpload(e.target.files)}
          className="hidden"
        />
        <div className="p-3.5 rounded-2xl bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 group-hover:scale-110 transition mb-3">
          <Upload className="h-6 w-6" />
        </div>
        <div className="text-sm font-semibold text-slate-200 mb-1">
          {uploading ? 'Processing & Ingesting Chunks…' : 'Click or Drag & Drop Documents to Ingest'}
        </div>
        <p className="text-xs text-slate-400 max-w-sm">
          Supports <span className="text-indigo-400 font-semibold">PDF (with page markers)</span>,{' '}
          <span className="text-indigo-400 font-semibold">TXT</span>, and{' '}
          <span className="text-indigo-400 font-semibold">Markdown</span> files.
        </p>
      </div>

      {/* Document List Header & Search */}
      <div className="flex items-center justify-between gap-4 pt-2">
        <div className="text-xs font-semibold text-slate-400">
          {documents.length} Document(s) in Knowledge Base
        </div>
        <div className="relative w-full max-w-xs">
          <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search documents…"
            className="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {/* Documents Table */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 overflow-hidden shadow-lg">
        {loading ? (
          <div className="p-8 text-center text-xs text-slate-400">Loading documents…</div>
        ) : filteredDocs.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            No documents found. Upload documents to get started.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 border-b border-slate-800 text-slate-400 font-semibold">
                <tr>
                  <th className="py-3 px-4">Filename</th>
                  <th className="py-3 px-4">Chunks</th>
                  <th className="py-3 px-4">Size</th>
                  <th className="py-3 px-4">Uploaded</th>
                  <th className="py-3 px-4">Owner</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {filteredDocs.map((doc) => {
                  const sizeKb = (doc.source_size_bytes / 1024).toFixed(1);
                  const uploadDate = doc.uploaded_at
                    ? new Date(doc.uploaded_at).toLocaleDateString()
                    : '—';

                  return (
                    <tr key={doc.document_id} className="hover:bg-slate-850/50 transition">
                      <td className="py-3 px-4 font-medium text-white flex items-center gap-2.5">
                        {getFileIcon(doc.file_extension)}
                        <span className="truncate max-w-[200px] sm:max-w-xs">{doc.filename}</span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded bg-indigo-950/50 text-indigo-300 border border-indigo-500/20 font-mono">
                          {doc.chunks}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-400">{sizeKb} KB</td>
                      <td className="py-3 px-4 text-slate-400">{uploadDate}</td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[10px]">
                          {doc.owner_id}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right space-x-2">
                        <button
                          onClick={() => onInspectDocument(doc.document_id)}
                          className="px-2.5 py-1 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 transition text-xs"
                          title="Inspect Chunks"
                        >
                          Inspect
                        </button>
                        <button
                          onClick={() => handleDelete(doc.document_id, doc.filename)}
                          className="p-1.5 rounded-lg bg-slate-800 hover:bg-red-950/50 text-slate-400 hover:text-red-400 transition"
                          title="Delete Document"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
