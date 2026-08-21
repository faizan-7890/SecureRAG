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
} from 'lucide-react';
import type { ApiClient } from '../api/client';
import type { ChatMessage, Source } from '../types';

interface ChatWorkspaceProps {
  api: ApiClient;
  sessionId: string;
  onResetSession: () => void;
}

export const ChatWorkspace: React.FC<ChatWorkspaceProps> = ({
  api,
  sessionId,
  onResetSession,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

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

  const handleSend = async (queryText?: string) => {
    const question = (queryText || input).trim();
    if (!question || isStreaming) return;

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

    setMessages((prev) => [...prev, userMessage, initialAssistantMessage]);
    setIsStreaming(true);

    let accumulatedContent = '';
    let accumulatedSources: Source[] = [];

    await api.streamChat(
      question,
      messages,
      sessionId,
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
        if (cached) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId ? { ...msg, cached: true } : msg
            )
          );
        }
      }
    );
  };

  const toggleSources = (msgId: string) => {
    setExpandedSources((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  const handleExportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(messages, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `securerag-chat-${sessionId.slice(0, 8)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4.5rem)] max-w-5xl mx-auto px-4 py-4">
      {/* Top action bar */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/80 text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 bg-indigo-950/40 text-indigo-300 border border-indigo-500/20 px-2 py-0.5 rounded-md">
            <Layers className="h-3 w-3" /> Hybrid Search Active
          </span>
          <span className="flex items-center gap-1 bg-slate-900 px-2 py-0.5 rounded-md border border-slate-800">
            Session: <code className="text-slate-300">{sessionId.slice(0, 8)}…</code>
          </span>
        </div>
        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <>
              <button
                onClick={handleExportJson}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 transition"
              >
                <Download className="h-3.5 w-3.5" /> Export
              </button>
              <button
                onClick={() => {
                  setMessages([]);
                  onResetSession();
                }}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-red-950/40 text-slate-400 hover:text-red-400 border border-slate-800 transition"
              >
                <Trash2 className="h-3.5 w-3.5" /> Clear
              </button>
            </>
          )}
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto py-4 space-y-6">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="p-4 rounded-2xl bg-gradient-to-br from-indigo-500/10 to-purple-500/10 border border-indigo-500/20 mb-4 shadow-xl shadow-indigo-500/5">
              <Sparkles className="h-8 w-8 text-indigo-400 animate-pulse" />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Welcome to SecureRAG</h2>
            <p className="text-sm text-slate-400 max-w-md mb-8">
              Ask questions over your private documents. Answers are grounded with strict citation tracebacks.
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
          messages.map((msg) => (
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
                            className="rounded-xl bg-slate-950/80 p-3 border border-indigo-500/20 text-xs"
                          >
                            <div className="flex items-center justify-between font-semibold text-indigo-300 mb-1.5">
                              <span>📄 {src.filename}</span>
                              <div className="flex gap-1.5 text-[10px]">
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
                              </div>
                            </div>
                            <p className="text-slate-300 bg-slate-900/60 p-2 rounded-lg border-l-2 border-indigo-500 font-sans leading-relaxed">
                              "{src.excerpt}"
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {msg.role === 'user' && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-slate-300 border border-slate-700">
                  <User className="h-4 w-4" />
                </div>
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Box */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="mt-2"
      >
        <div className="relative flex items-center rounded-2xl bg-slate-900 border border-slate-800 focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500 p-1.5 shadow-lg">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about your documents…"
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
  );
};
