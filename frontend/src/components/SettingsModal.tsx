import React from 'react';
import { X, Settings as SettingsIcon, Sliders, Key, Server, Cpu } from 'lucide-react';
import type { RuntimeSettings } from '../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: RuntimeSettings;
  onUpdateSettings: (newSettings: RuntimeSettings) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onUpdateSettings,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl p-6 relative animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="flex items-center gap-3 mb-6">
          <div className="p-2.5 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400">
            <SettingsIcon className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">System Settings & Parameters</h3>
            <p className="text-xs text-slate-400">Configure RAG pipeline and runtime connection.</p>
          </div>
        </div>

        <div className="space-y-5 text-xs">
          {/* Connection */}
          <div className="space-y-2">
            <label className="flex items-center gap-1.5 font-semibold text-slate-300">
              <Server className="h-3.5 w-3.5 text-indigo-400" />
              <span>FastAPI Backend URL</span>
            </label>
            <input
              type="text"
              value={settings.apiUrl}
              onChange={(e) => onUpdateSettings({ ...settings, apiUrl: e.target.value })}
              placeholder="http://127.0.0.1:8000"
              className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white font-mono focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* API Key Override */}
          <div className="space-y-2">
            <label className="flex items-center gap-1.5 font-semibold text-slate-300">
              <Key className="h-3.5 w-3.5 text-purple-400" />
              <span>OpenAI / Google Gemini API Key (Session Override)</span>
            </label>
            <input
              type="password"
              value={settings.apiKey}
              onChange={(e) => onUpdateSettings({ ...settings, apiKey: e.target.value })}
              placeholder="sk-... or AIzaSy... (leave empty to use server .env)"
              className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white font-mono focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* Search Strategies */}
          <div className="space-y-3 pt-2 border-t border-slate-800">
            <div className="flex items-center gap-1.5 font-semibold text-slate-300">
              <Sliders className="h-3.5 w-3.5 text-indigo-400" />
              <span>Retrieval & Generation Switches</span>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-850">
              <div>
                <div className="font-semibold text-slate-200">Real-Time Token Streaming (SSE)</div>
                <div className="text-[11px] text-slate-400">Stream response tokens as they are generated.</div>
              </div>
              <input
                type="checkbox"
                checked={settings.streaming}
                onChange={(e) => onUpdateSettings({ ...settings, streaming: e.target.checked })}
                className="h-4 w-4 rounded accent-indigo-600"
              />
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-850">
              <div>
                <div className="font-semibold text-slate-200">Hybrid Search (BM25 + Dense)</div>
                <div className="text-[11px] text-slate-400">Reciprocal Rank Fusion of keyword & semantic vectors.</div>
              </div>
              <input
                type="checkbox"
                checked={settings.hybridSearch}
                onChange={(e) => onUpdateSettings({ ...settings, hybridSearch: e.target.checked })}
                className="h-4 w-4 rounded accent-indigo-600"
              />
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-850">
              <div>
                <div className="font-semibold text-slate-200">Multi-Query Expansion</div>
                <div className="text-[11px] text-slate-400">Generate sub-queries to broaden search context.</div>
              </div>
              <input
                type="checkbox"
                checked={settings.queryExpansion}
                onChange={(e) => onUpdateSettings({ ...settings, queryExpansion: e.target.checked })}
                className="h-4 w-4 rounded accent-indigo-600"
              />
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-850">
              <div>
                <div className="font-semibold text-slate-200">Two-Stage Cross-Encoder Reranker</div>
                <div className="text-[11px] text-slate-400">Deep cross-attention scoring (ms-marco-MiniLM-L-6-v2).</div>
              </div>
              <input
                type="checkbox"
                checked={settings.enableReranker}
                onChange={(e) => onUpdateSettings({ ...settings, enableReranker: e.target.checked })}
                className="h-4 w-4 rounded accent-indigo-600"
              />
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-850">
              <div>
                <div className="font-semibold text-slate-200">Semantic Response Cache</div>
                <div className="text-[11px] text-slate-400">Sub-10ms instant response cache on high similarity (≥0.96).</div>
              </div>
              <input
                type="checkbox"
                checked={settings.enableSemanticCache}
                onChange={(e) => onUpdateSettings({ ...settings, enableSemanticCache: e.target.checked })}
                className="h-4 w-4 rounded accent-indigo-600"
              />
            </div>
          </div>

          {/* Model Topology */}
          <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5 text-[11px] text-slate-400">
            <div className="flex items-center gap-1.5 font-semibold text-slate-200 mb-1">
              <Cpu className="h-3.5 w-3.5 text-indigo-400" />
              <span>Active Architecture Stack</span>
            </div>
            <div>• <b>Embeddings:</b> <code>sentence-transformers/all-MiniLM-L6-v2</code> (384-d, CPU)</div>
            <div>• <b>Dense Vector Store:</b> Chroma DB Persistence</div>
            <div>• <b>Sparse Lexical Index:</b> Okapi BM25 with JSON stats</div>
            <div>• <b>Reranker:</b> <code>cross-encoder/ms-marco-MiniLM-L-6-v2</code></div>
            <div>• <b>Semantic Cache:</b> In-memory + Disk JSON (threshold: 0.96)</div>
            <div>• <b>Rank Fusion:</b> Reciprocal Rank Fusion (k=60, dense:0.6, sparse:0.4)</div>
          </div>
        </div>

        <button
          onClick={onClose}
          className="mt-6 w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition shadow-lg shadow-indigo-600/20"
        >
          Save & Close
        </button>
      </div>
    </div>
  );
};
