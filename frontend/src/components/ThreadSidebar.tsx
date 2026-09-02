import React, { useState } from 'react';
import {
  Plus,
  MessageSquare,
  Trash2,
  Search,
  X,
  Clock,
} from 'lucide-react';
import type { ChatThread } from '../types';

interface ThreadSidebarProps {
  threads: ChatThread[];
  activeThreadId: string;
  onSelectThread: (threadId: string) => void;
  onNewThread: () => void;
  onDeleteThread: (threadId: string) => void;
  isOpen: boolean;
  onClose: () => void;
}

export const ThreadSidebar: React.FC<ThreadSidebarProps> = ({
  threads,
  activeThreadId,
  onSelectThread,
  onNewThread,
  onDeleteThread,
  isOpen,
  onClose,
}) => {
  const [search, setSearch] = useState('');

  const filteredThreads = threads.filter((t) =>
    t.title.toLowerCase().includes(search.toLowerCase())
  );

  const formatTimestamp = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffMin = Math.round(diffMs / 60000);
      if (diffMin < 1) return 'Just now';
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHrs = Math.round(diffMin / 60);
      if (diffHrs < 24) return `${diffHrs}h ago`;
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-30 bg-slate-950/60 backdrop-blur-xs md:hidden"
        />
      )}

      <aside
        className={`fixed md:static inset-y-16 left-0 z-30 w-72 bg-slate-950 border-r border-slate-800/90 flex flex-col transform transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0 md:w-72'
        }`}
      >
        {/* Header / New Chat */}
        <div className="p-3 border-b border-slate-800/80 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
              Conversations
            </span>
            <button
              onClick={onClose}
              className="md:hidden p-1 text-slate-400 hover:text-white rounded"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <button
            onClick={() => {
              onNewThread();
              if (window.innerWidth < 768) onClose();
            }}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/30 transition group"
          >
            <Plus className="h-4 w-4 group-hover:rotate-90 transition-transform duration-200" />
            New Chat Thread
          </button>

          {/* Search filter */}
          {threads.length > 2 && (
            <div className="relative">
              <Search className="h-3.5 w-3.5 absolute left-2.5 top-2.5 text-slate-500" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter chats..."
                className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>
          )}
        </div>

        {/* Thread List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {filteredThreads.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-500">
              {search ? 'No matching chats' : 'No saved conversations yet'}
            </div>
          ) : (
            filteredThreads.map((thread) => {
              const isActive = thread.id === activeThreadId;
              const msgCount = thread.messages.length;

              return (
                <div
                  key={thread.id}
                  onClick={() => {
                    onSelectThread(thread.id);
                    if (window.innerWidth < 768) onClose();
                  }}
                  className={`group relative flex items-center justify-between p-2.5 rounded-xl cursor-pointer transition text-xs ${
                    isActive
                      ? 'bg-indigo-950/50 text-indigo-200 border border-indigo-500/30 shadow-sm'
                      : 'text-slate-300 hover:bg-slate-900 hover:text-white border border-transparent'
                  }`}
                >
                  <div className="flex items-start gap-2.5 min-w-0 pr-2">
                    <MessageSquare
                      className={`h-4 w-4 shrink-0 mt-0.5 ${
                        isActive ? 'text-indigo-400' : 'text-slate-500 group-hover:text-slate-400'
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate text-slate-200 group-hover:text-white">
                        {thread.title}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
                        <span className="flex items-center gap-1">
                          <Clock className="h-2.5 w-2.5" />
                          {formatTimestamp(thread.updatedAt)}
                        </span>
                        <span>•</span>
                        <span>{msgCount} msgs</span>
                      </div>
                    </div>
                  </div>

                  {/* Delete action */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteThread(thread.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-950/40 transition"
                    title="Delete Chat"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-800/80 text-[11px] text-slate-500 flex items-center justify-between">
          <span>{threads.length} saved {threads.length === 1 ? 'chat' : 'chats'}</span>
          <span className="text-indigo-400/80">Local Encrypted</span>
        </div>
      </aside>
    </>
  );
};
