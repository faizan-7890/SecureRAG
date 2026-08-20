import React from 'react';
import {
  Shield,
  MessageSquare,
  FileText,
  Search,
  Users,
  BarChart3,
  Settings,
  LogIn,
  LogOut,
} from 'lucide-react';
import type { UserProfile } from '../types';

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  user: UserProfile | null;
  serverStatus: { status: string; latencyMs: number } | null;
  onOpenAuth: () => void;
  onLogout: () => void;
  onOpenSettings: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  user,
  serverStatus,
  onOpenAuth,
  onLogout,
  onOpenSettings,
}) => {
  const navItems = [
    { id: 'chat', label: 'Chat', icon: MessageSquare },
    { id: 'documents', label: 'Documents', icon: FileText },
    { id: 'inspector', label: 'Chunk Inspector', icon: Search },
    { id: 'admin', label: 'RBAC Admin', icon: Users, requiresAdmin: false },
    { id: 'benchmarks', label: 'Evaluation', icon: BarChart3 },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-indigo-950/40 bg-slate-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-indigo-500/20">
            <Shield className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-indigo-400 via-indigo-200 to-purple-300 bg-clip-text text-transparent">
                SecureRAG
              </span>
              <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] font-semibold text-indigo-400 border border-indigo-500/20">
                v1.0 (Bun)
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">Enterprise Grounded AI</p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="hidden md:flex items-center gap-1 bg-slate-900/60 p-1 rounded-xl border border-slate-800/80">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Right Side: Health, User & Settings */}
        <div className="flex items-center gap-3">
          {/* Health Pill */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs text-slate-300">
            <span
              className={`h-2 w-2 rounded-full ${
                serverStatus ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'
              }`}
            />
            <span className="hidden sm:inline">
              {serverStatus ? `${serverStatus.latencyMs}ms` : 'Offline'}
            </span>
          </div>

          {/* Settings Button */}
          <button
            onClick={onOpenSettings}
            className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition"
            title="Settings & Diagnostics"
          >
            <Settings className="h-4 w-4" />
          </button>

          {/* User Profile / Auth */}
          {user ? (
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2 pl-2 pr-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs">
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    user.role === 'admin'
                      ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                      : 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                  }`}
                >
                  {user.role.toUpperCase()}
                </span>
                <span className="font-medium text-slate-200">{user.username}</span>
              </div>
              <button
                onClick={onLogout}
                className="p-2 rounded-lg bg-slate-900 hover:bg-red-950/40 text-slate-400 hover:text-red-400 border border-slate-800 transition"
                title="Log Out"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={onOpenAuth}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white shadow-md shadow-indigo-600/20 transition"
            >
              <LogIn className="h-3.5 w-3.5" />
              Sign In
            </button>
          )}
        </div>
      </div>

      {/* Mobile Nav Bar */}
      <div className="flex md:hidden border-t border-slate-800 bg-slate-950 px-2 py-1 overflow-x-auto gap-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`flex items-center gap-1 px-3 py-1.5 rounded-md text-xs whitespace-nowrap ${
                isActive ? 'bg-indigo-600 text-white' : 'text-slate-400'
              }`}
            >
              <Icon className="h-3 w-3" />
              {item.label}
            </button>
          );
        })}
      </div>
    </header>
  );
};
