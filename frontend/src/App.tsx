import React, { useState, useEffect, useMemo } from 'react';
import { Navbar } from './components/Navbar';
import { ChatWorkspace } from './components/ChatWorkspace';
import { DocumentManager } from './components/DocumentManager';
import { ChunkInspector } from './components/ChunkInspector';
import { AdminConsole } from './components/AdminConsole';
import { BenchmarksDashboard } from './components/BenchmarksDashboard';
import { AuthModal } from './components/AuthModal';
import { SettingsModal } from './components/SettingsModal';
import { ApiClient } from './api/client';
import type { RuntimeSettings, UserProfile } from './types';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('chat');
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID());

  // Auth State
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('securerag_token'));
  const [user, setUser] = useState<UserProfile | null>(() => {
    const cached = localStorage.getItem('securerag_user');
    return cached ? JSON.parse(cached) : null;
  });
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  // Settings State
  const [settings, setSettings] = useState<RuntimeSettings>(() => {
    const saved = localStorage.getItem('securerag_settings');
    const parsed = saved ? JSON.parse(saved) : {};
    return {
      apiUrl: parsed.apiUrl || 'http://127.0.0.1:8000',
      apiKey: parsed.apiKey || '',
      streaming: parsed.streaming !== undefined ? parsed.streaming : true,
      hybridSearch: parsed.hybridSearch !== undefined ? parsed.hybridSearch : true,
      queryExpansion: parsed.queryExpansion !== undefined ? parsed.queryExpansion : false,
      enableReranker: parsed.enableReranker !== undefined ? parsed.enableReranker : true,
      enableSemanticCache: parsed.enableSemanticCache !== undefined ? parsed.enableSemanticCache : true,
    };
  });
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Server Health
  const [serverStatus, setServerStatus] = useState<{ status: string; latencyMs: number } | null>(null);

  // ApiClient Singleton
  const api = useMemo(() => new ApiClient(settings, token), []);

  useEffect(() => {
    api.update(settings, token);
    localStorage.setItem('securerag_settings', JSON.stringify(settings));
  }, [settings, token, api]);

  // Health poll
  useEffect(() => {
    const checkHealth = async () => {
      const status = await api.getHealth();
      setServerStatus(status);
    };
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, [api]);

  // Fetch current user if token exists
  useEffect(() => {
    if (token && !user) {
      api
        .getMe()
        .then((profile) => {
          setUser(profile);
          localStorage.setItem('securerag_user', JSON.stringify(profile));
        })
        .catch(() => {
          setToken(null);
          setUser(null);
          localStorage.removeItem('securerag_token');
          localStorage.removeItem('securerag_user');
        });
    }
  }, [token, user, api]);

  const handleAuthSuccess = (newToken: string, profile: UserProfile) => {
    setToken(newToken);
    setUser(profile);
    localStorage.setItem('securerag_token', newToken);
    localStorage.setItem('securerag_user', JSON.stringify(profile));
  };

  const handleLogout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('securerag_token');
    localStorage.removeItem('securerag_user');
  };

  const handleInspectDocument = (docId: string) => {
    setSelectedDocId(docId);
    setActiveTab('inspector');
  };

  const handleResetSession = () => {
    setSessionId(crypto.randomUUID());
  };

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 flex flex-col selection:bg-indigo-500 selection:text-white">
      {/* Navigation */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        user={user}
        serverStatus={serverStatus}
        onOpenAuth={() => setIsAuthOpen(true)}
        onLogout={handleLogout}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      {/* Main Views */}
      <main className="flex-1">
        {activeTab === 'chat' && (
          <ChatWorkspace
            api={api}
            sessionId={sessionId}
            onResetSession={handleResetSession}
          />
        )}

        {activeTab === 'documents' && (
          <DocumentManager
            api={api}
            onInspectDocument={handleInspectDocument}
          />
        )}

        {activeTab === 'inspector' && (
          <ChunkInspector
            api={api}
            selectedDocId={selectedDocId}
          />
        )}

        {activeTab === 'admin' && (
          <AdminConsole
            api={api}
            currentUser={user}
          />
        )}

        {activeTab === 'benchmarks' && <BenchmarksDashboard />}
      </main>

      {/* Modals */}
      <AuthModal
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
        api={api}
        onSuccess={handleAuthSuccess}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onUpdateSettings={setSettings}
      />
    </div>
  );
};

export default App;
