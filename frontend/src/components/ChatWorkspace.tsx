import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Sparkles,
  Bot,
  User,
  BookOpen,
  Download,
  Trash2,
  ChevronDown,
  ChevronUp,
  Layers,
  Search,
  Zap,
  ThumbsUp,
  ThumbsDown,
  Copy,
  Check,
  Filter,
  PanelLeft,
  RotateCcw,
  FileText,
  ExternalLink,
} from 'lucide-react';
import type { ApiClient } from '../api/client';
import type { ChatMessage, ChatThread, DocumentRecord, Source } from '../types';
import { ThreadSidebar } from './ThreadSidebar';
import { CitationDrawer } from './CitationDrawer';

interface ChatWorkspaceProps {
  api: ApiClient;
  sessionId: string;
  onResetSession: () => void;
  onInspectDocument?: (documentId: string) => void;
}

export const ChatWorkspace: React.FC<ChatWorkspaceProps> = ({
  api,
  sessionId,
  onResetSession,
  onInspectDocument,
}) => {
  // Thread State
  const [threads, setThreads] = useState<ChatThread[]>(() => {
    try {
      const saved = localStorage.getItem('securerag_chat_threads');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // fallback
    }
    return [
      {
        id: sessionId,
        title: 'New Conversation',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: [],
      },
    ];
  });

  const [activeThreadId, setActiveThreadId] = useState<string>(() => {
    const saved = localStorage.getItem('securerag_active_thread_id');
    return saved || sessionId;
  });

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);

  // Document Scoping & Available docs
  const [availableDocs, setAvailableDocs] = useState<DocumentRecord[]>([]);
  const [selectedDocScope, setSelectedDocScope] = useState<string>('all');

  // Citation Drawer State
  const [inspectingSource, setInspectingSource] = useState<Source | null>(null);
  const [inspectingQuery, setInspectingQuery] = useState<string>('');
  const [isCitationDrawerOpen, setIsCitationDrawerOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load available documents for filter scope
  useEffect(() => {
    api
      .listDocuments()
      .then((docs) => setAvailableDocs(docs))
      .catch(() => {});
  }, [api]);

  // Sync active thread messages on activeThreadId change
  useEffect(() => {
    const current = threads.find((t) => t.id === activeThreadId);
    if (current) {
      setMessages(current.messages);
      setSelectedDocScope(current.scopeDocument || 'all');
    } else if (threads.length > 0) {
      setActiveThreadId(threads[0].id);
      setMessages(threads[0].messages);
    }
    localStorage.setItem('securerag_active_thread_id', activeThreadId);
  }, [activeThreadId, threads]);

  // Persist threads to localStorage
  const persistThreads = (updatedThreads: ChatThread[]) => {
    setThreads(updatedThreads);
    try {
      localStorage.setItem('securerag_chat_threads', JSON.stringify(updatedThreads));
    } catch {
      // ignore
    }
  };

  const starterPrompts = [
    { label: '🌴 Annual Leave Policy', query: 'How many days of annual leave do full-time employees receive?' },
    { label: '🏡 Remote Work Rules', query: 'How many days per week can employees work remotely and what is the stipend?' },
    { label: '✈️ Travel Expense Limits', query: 'What is the daily meal limit for international business travel?' },
    { label: '📈 Performance PIP Rules', query: 'What happens to employees who receive a performance rating of 1 or 2?' },
  ];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming]);

  // Thread Operations
  const handleNewThread = () => {
    const newId = crypto.randomUUID();
    const newThread: ChatThread = {
      id: newId,
      title: 'New Conversation',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [],
      scopeDocument: 'all',
    };
    const updated = [newThread, ...threads];
    persistThreads(updated);
    setActiveThreadId(newId);
    setMessages([]);
    onResetSession();
  };

  const handleDeleteThread = (threadId: string) => {
    const updated = threads.filter((t) => t.id !== threadId);
    if (updated.length === 0) {
      const fallbackId = crypto.randomUUID();
      const fallback: ChatThread = {
        id: fallbackId,
        title: 'New Conversation',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: [],
      };
      persistThreads([fallback]);
      setActiveThreadId(fallbackId);
      setMessages([]);
    } else {
      persistThreads(updated);
      if (activeThreadId === threadId) {
        setActiveThreadId(updated[0].id);
        setMessages(updated[0].messages);
      }
    }
  };

  const handleSend = async (queryText?: string) => {
    let question = (queryText || input).trim();
    if (!question || isStreaming) return;

    // Apply document scope filter if specific document selected
    let effectiveQuestion = question;
    if (selectedDocScope !== 'all') {
      const targetDoc = availableDocs.find((d) => d.document_id === selectedDocScope);
      if (targetDoc) {
        effectiveQuestion = `[Filter document: ${targetDoc.filename}] ${question}`;
      }
    }

    setInput('');
    const userMsgId = crypto.randomUUID();
    const assistantMsgId = crypto.randomUUID();

    const userMessage: ChatMessage = {
      id: userMsgId,
      role: 'user',
      content: question,
      timestamp: new Date().toLocaleTimeString(),
    };

    const initialAssistantMessage: ChatMessage = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      sources: [],
      timestamp: new Date().toLocaleTimeString(),
    };

    const nextMessages = [...messages, userMessage, initialAssistantMessage];
    setMessages(nextMessages);
    setIsStreaming(true);

    let accumulatedContent = '';
    let accumulatedSources: Source[] = [];

    await api.streamChat(
      effectiveQuestion,
      messages,
      activeThreadId,
      (token) => {
        accumulatedContent += token;
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId ? { ...msg, content: accumulatedContent } : msg
          )
        );
      },
      (sources) => {
        accumulatedSources = sources;
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId ? { ...msg, sources: accumulatedSources } : msg
          )
        );
      },
      (error) => {
        accumulatedContent += `\n\n⚠️ **Error:** ${error}`;
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId ? { ...msg, content: accumulatedContent } : msg
          )
        );
      },
      (cached) => {
        setIsStreaming(false);

        // Update active thread in storage
        const updatedMsgs = nextMessages.map((msg) =>
          msg.id === assistantMsgId
            ? {
                ...msg,
                content: accumulatedContent,
                sources: accumulatedSources,
                cached: !!cached,
              }
            : msg
        );

        const threadTitle =
          messages.length === 0
            ? question.slice(0, 36) + (question.length > 36 ? '...' : '')
            : threads.find((t) => t.id === activeThreadId)?.title || 'Conversation';

        const updatedThreads = threads.map((t) =>
          t.id === activeThreadId
            ? {
                ...t,
                title: t.messages.length === 0 ? threadTitle : t.title,
                updatedAt: new Date().toISOString(),
                messages: updatedMsgs,
                scopeDocument: selectedDocScope,
              }
            : t
        );
        persistThreads(updatedThreads);
      }
    );
  };

  const toggleSources = (msgId: string) => {
    setExpandedSources((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  const handleCopyMessage = (msgId: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedMsgId(msgId);
    setTimeout(() => setCopiedMsgId(null), 2000);
  };

  const handleFeedback = (msgId: string, rating: 'up' | 'down') => {
    const updated = messages.map((m) =>
      m.id === msgId ? { ...m, feedback: m.feedback === rating ? null : rating } : m
    );
    setMessages(updated);

    const updatedThreads = threads.map((t) =>
      t.id === activeThreadId ? { ...t, messages: updated } : t
    );
    persistThreads(updatedThreads);
  };

  const handleOpenCitation = (source: Source, query: string) => {
    setInspectingSource(source);
    setInspectingQuery(query);
    setIsCitationDrawerOpen(true);
  };

  const handleExportMarkdown = () => {
    let md = `# SecureRAG Chat Session\n\n` +
      `- **Thread ID:** \`${activeThreadId}\`\n` +
      `- **Export Date:** ${new Date().toLocaleString()}\n` +
      `- **Total Messages:** ${messages.length}\n\n---\n\n`;

    for (const msg of messages) {
      if (msg.role === 'user') {
        md += `### 👤 User (${msg.timestamp})\n\n${msg.content}\n\n`;
      } else {
        md += `### 🤖 Assistant (${msg.timestamp})\n\n${msg.content}\n\n`;
        if (msg.sources && msg.sources.length > 0) {
          md += `#### Grounded Citations:\n`;
          msg.sources.forEach((s, idx) => {
            md += `${idx + 1}. **${s.filename}** (Page ${s.page ?? 'N/A'}, Chunk #${s.chunk_index ?? 'N/A'}, Relevance: ${s.relevance_score?.toFixed(3) ?? 'N/A'})\n`;
            md += `   > "${s.excerpt}"\n\n`;
          });
        }
        md += `---\n\n`;
      }
    }

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `securerag-chat-${activeThreadId.slice(0, 8)}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportJson = () => {
    const dataStr =
      'data:text/json;charset=utf-8,' +
      encodeURIComponent(JSON.stringify({ threadId: activeThreadId, messages }, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `securerag-chat-${activeThreadId.slice(0, 8)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] w-full overflow-hidden bg-[#0b0f19]">
      {/* Multi-Chat Thread Sidebar */}
      <ThreadSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelectThread={setActiveThreadId}
        onNewThread={handleNewThread}
        onDeleteThread={handleDeleteThread}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      {/* Main Chat Workspace */}
      <div className="flex-1 flex flex-col h-full min-w-0">
        {/* Top action bar */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800/80 bg-slate-950/40 text-xs text-slate-400">
          <div className="flex items-center gap-2 overflow-hidden">
            {/* Sidebar toggle button */}
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 transition"
              title="Toggle Conversations"
            >
              <PanelLeft className="h-3.5 w-3.5" />
            </button>

            <span className="flex items-center gap-1 bg-indigo-950/40 text-indigo-300 border border-indigo-500/20 px-2 py-0.5 rounded-md shrink-0">
              <Layers className="h-3 w-3" /> Hybrid Search
            </span>

            <span className="hidden sm:flex items-center gap-1 bg-slate-900 px-2 py-0.5 rounded-md border border-slate-800 text-slate-300 shrink-0">
              Session: <code className="text-indigo-300 font-mono">{activeThreadId.slice(0, 8)}</code>
            </span>
          </div>

          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <>
                <button
                  onClick={handleExportMarkdown}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 transition"
                  title="Export Markdown Document"
                >
                  <Download className="h-3.5 w-3.5 text-indigo-400" />
                  <span className="hidden sm:inline">Markdown</span>
                </button>
                <button
                  onClick={handleExportJson}
                  className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition text-[11px]"
                  title="Export JSON"
                >
                  JSON
                </button>
                <button
                  onClick={() => {
                    setMessages([]);
                    const updated = threads.map((t) =>
                      t.id === activeThreadId ? { ...t, messages: [] } : t
                    );
                    persistThreads(updated);
                  }}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-red-950/40 text-slate-400 hover:text-red-400 border border-slate-800 transition"
                  title="Clear Current Messages"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Clear</span>
                </button>
              </>
            )}
          </div>
        </div>

        {/* Messages Scroll Area */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6 max-w-4xl mx-auto w-full">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-4 py-8">
              <div className="p-4 rounded-2xl bg-gradient-to-br from-indigo-500/10 to-purple-500/10 border border-indigo-500/20 mb-4 shadow-xl shadow-indigo-500/5">
                <Sparkles className="h-8 w-8 text-indigo-400 animate-pulse" />
              </div>
              <h2 className="text-xl font-bold text-white mb-2">Welcome to SecureRAG</h2>
              <p className="text-sm text-slate-400 max-w-md mb-8">
                Ask questions over private enterprise documents with strict source citations, hybrid search, and semantic caching.
              </p>

              {/* Quick Starters */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-2xl">
                {starterPrompts.map((p, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(p.query)}
                    className="flex items-start gap-2.5 p-3 rounded-xl bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-indigo-500/40 text-left transition group shadow-sm"
                  >
                    <Search className="h-4 w-4 text-indigo-400 shrink-0 mt-0.5 group-hover:scale-110 transition" />
                    <div>
                      <div className="text-xs font-semibold text-slate-200">{p.label}</div>
                      <div className="text-[11px] text-slate-400 line-clamp-1">{p.query}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg, index) => {
              const lastUserQuery = [...messages]
                .slice(0, index + 1)
                .reverse()
                .find((m) => m.role === 'user')?.content || '';

              return (
                <div
                  key={msg.id}
                  className={`flex gap-3.5 ${
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {msg.role === 'assistant' && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-600/30">
                      <Bot className="h-4 w-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-br-none shadow-lg shadow-indigo-600/20'
                        : 'bg-slate-900 border border-slate-800 text-slate-100 rounded-bl-none shadow-sm'
                    }`}
                  >
                    {msg.cached && (
                      <div className="flex items-center gap-1.5 text-[10px] font-bold text-amber-400 mb-1.5 bg-amber-950/40 border border-amber-500/20 px-2 py-0.5 rounded-full w-fit">
                        <Zap className="h-3 w-3" /> Semantic Cache (Instant)
                      </div>
                    )}

                    <div className="whitespace-pre-wrap">{msg.content || (isStreaming ? 'Thinking…' : '')}</div>

                    {/* Grounded Citation Sources */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-slate-800/80">
                        <button
                          onClick={() => toggleSources(msg.id)}
                          className="flex items-center gap-1.5 text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition"
                        >
                          <BookOpen className="h-3.5 w-3.5" />
                          <span>{msg.sources.length} Grounded Source Citation(s)</span>
                          {expandedSources[msg.id] ? (
                            <ChevronUp className="h-3.5 w-3.5 ml-1" />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5 ml-1" />
                          )}
                        </button>

                        {expandedSources[msg.id] && (
                          <div className="mt-2 space-y-2">
                            {msg.sources.map((src, i) => (
                              <div
                                key={i}
                                onClick={() => handleOpenCitation(src, lastUserQuery)}
                                className="group/src rounded-xl bg-slate-950/90 p-3 border border-indigo-500/20 hover:border-indigo-500/50 cursor-pointer transition text-xs shadow-xs"
                              >
                                <div className="flex items-center justify-between font-semibold text-indigo-300 mb-1.5">
                                  <span className="flex items-center gap-1.5 group-hover/src:text-indigo-200">
                                    <FileText className="h-3.5 w-3.5 text-indigo-400" />
                                    {src.filename}
                                  </span>
                                  <div className="flex items-center gap-1.5 text-[10px]">
                                    {src.page && (
                                      <span className="bg-slate-800 px-1.5 py-0.5 rounded text-slate-300">
                                        Page {src.page}
                                      </span>
                                    )}
                                    {src.chunk_index !== undefined && (
                                      <span className="bg-slate-800 px-1.5 py-0.5 rounded text-slate-300">
                                        Chunk #{src.chunk_index}
                                      </span>
                                    )}
                                    {src.relevance_score !== undefined && (
                                      <span className="bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded font-mono">
                                        {src.relevance_score?.toFixed(3)}
                                      </span>
                                    )}
                                    <ExternalLink className="h-3 w-3 text-slate-500 group-hover/src:text-indigo-300 transition" />
                                  </div>
                                </div>
                                <p className="text-slate-300 bg-slate-900/60 p-2 rounded-lg border-l-2 border-indigo-500 font-sans leading-relaxed group-hover/src:bg-slate-900 transition">
                                  "{src.excerpt}"
                                </p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Message Actions Bar (for Assistant responses) */}
                    {msg.role === 'assistant' && msg.content && !isStreaming && (
                      <div className="flex items-center justify-between mt-3 pt-2 border-t border-slate-800/60 text-xs text-slate-400">
                        <span className="text-[11px] text-slate-500">{msg.timestamp}</span>

                        <div className="flex items-center gap-1">
                          {/* Copy button */}
                          <button
                            onClick={() => handleCopyMessage(msg.id, msg.content)}
                            className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
                            title="Copy response"
                          >
                            {copiedMsgId === msg.id ? (
                              <Check className="h-3.5 w-3.5 text-emerald-400" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                          </button>

                          {/* Thumbs Up */}
                          <button
                            onClick={() => handleFeedback(msg.id, 'up')}
                            className={`p-1.5 rounded-md transition ${
                              msg.feedback === 'up'
                                ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/30'
                                : 'hover:bg-slate-800 text-slate-400 hover:text-slate-200'
                            }`}
                            title="Helpful response"
                          >
                            <ThumbsUp className="h-3.5 w-3.5" />
                          </button>

                          {/* Thumbs Down */}
                          <button
                            onClick={() => handleFeedback(msg.id, 'down')}
                            className={`p-1.5 rounded-md transition ${
                              msg.feedback === 'down'
                                ? 'bg-red-950/60 text-red-400 border border-red-500/30'
                                : 'hover:bg-slate-800 text-slate-400 hover:text-slate-200'
                            }`}
                            title="Needs improvement"
                          >
                            <ThumbsDown className="h-3.5 w-3.5" />
                          </button>

                          {/* Re-send query */}
                          {lastUserQuery && (
                            <button
                              onClick={() => handleSend(lastUserQuery)}
                              className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
                              title="Regenerate response"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  {msg.role === 'user' && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-slate-300 border border-slate-700">
                      <User className="h-4 w-4" />
                    </div>
                  )}
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar & Scope Filter */}
        <div className="p-4 border-t border-slate-800/80 bg-slate-950/60 max-w-4xl mx-auto w-full">
          {/* Document Scope Filter */}
          <div className="flex items-center gap-2 mb-2 text-xs">
            <span className="flex items-center gap-1 text-slate-400 shrink-0">
              <Filter className="h-3 w-3 text-indigo-400" />
              Scope:
            </span>
            <select
              value={selectedDocScope}
              onChange={(e) => setSelectedDocScope(e.target.value)}
              className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="all">🌐 All Ingested Documents</option>
              {availableDocs.map((doc) => (
                <option key={doc.document_id} value={doc.document_id}>
                  📄 {doc.filename} ({doc.chunks} chunks)
                </option>
              ))}
            </select>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <div className="relative flex items-center rounded-2xl bg-slate-900 border border-slate-800 focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500 p-1.5 shadow-lg">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  selectedDocScope === 'all'
                    ? 'Ask a question across all documents…'
                    : `Ask a question specifically about selected document…`
                }
                disabled={isStreaming}
                className="flex-1 bg-transparent px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || isStreaming}
                className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-600/30 hover:bg-indigo-500 disabled:opacity-40 transition shrink-0"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Citation Inspector Side Drawer */}
      <CitationDrawer
        source={inspectingSource}
        searchQuery={inspectingQuery}
        isOpen={isCitationDrawerOpen}
        onClose={() => setIsCitationDrawerOpen(false)}
        onInspectDocument={(filename) => {
          const matched = availableDocs.find((d) => d.filename === filename);
          if (matched && onInspectDocument) {
            onInspectDocument(matched.document_id);
          }
        }}
      />
    </div>
  );
};
