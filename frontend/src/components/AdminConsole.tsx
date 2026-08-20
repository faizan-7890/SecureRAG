import React, { useState, useEffect } from 'react';
import { Shield, UserPlus, Users, AlertCircle, CheckCircle2 } from 'lucide-react';
import type { ApiClient } from '../api/client';
import type { UserProfile } from '../types';

interface AdminConsoleProps {
  api: ApiClient;
  currentUser: UserProfile | null;
}

export const AdminConsole: React.FC<AdminConsoleProps> = ({
  api,
  currentUser,
}) => {
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // New user form state
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('user');
  const [creating, setCreating] = useState(false);

  const loadUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const uList = await api.getUsers();
      setUsers(uList);
    } catch (err: any) {
      setError(err.message || 'Failed to load user directory');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (currentUser?.role === 'admin') {
      loadUsers();
    }
  }, [currentUser]);

  const handleRoleToggle = async (username: string, currentRole: string) => {
    const targetRole = currentRole === 'admin' ? 'user' : 'admin';
    try {
      await api.updateUserRole(username, targetRole);
      setSuccess(`Updated ${username}'s role to ${targetRole}.`);
      loadUsers();
    } catch (err: any) {
      setError(err.message || 'Failed to update user role');
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword.trim()) {
      setError('Please provide username and password.');
      return;
    }
    setCreating(true);
    setError(null);
    setSuccess(null);
    try {
      await api.register(newUsername, newPassword);
      if (newRole !== 'user') {
        await api.updateUserRole(newUsername, newRole);
      }
      setSuccess(`User '${newUsername}' created with role '${newRole}'.`);
      setNewUsername('');
      setNewPassword('');
      setNewRole('user');
      loadUsers();
    } catch (err: any) {
      setError(err.message || 'Failed to create user');
    } finally {
      setCreating(false);
    }
  };

  if (currentUser?.role !== 'admin') {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 inline-block mb-4">
          <Shield className="h-8 w-8" />
        </div>
        <h3 className="text-lg font-bold text-white mb-2">Administrator Access Required</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto">
          You must be logged in as an Administrator (e.g. bootstrap admin) to manage users and access control policies.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* Title */}
      <div>
        <h2 className="text-xl font-bold text-white">RBAC & User Administration</h2>
        <p className="text-xs text-slate-400">
          Manage user accounts, assign role permissions, and review security isolation policies.
        </p>
      </div>

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* User Directory */}
        <div className="lg:col-span-2 rounded-2xl bg-slate-900 border border-slate-800 p-5 space-y-4 shadow-lg">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-semibold text-sm text-white">
              <Users className="h-4 w-4 text-indigo-400" />
              <span>User Directory ({users.length})</span>
            </div>
            <button
              onClick={loadUsers}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <div className="p-8 text-center text-xs text-slate-400">Loading user accounts…</div>
          ) : (
            <div className="divide-y divide-slate-800/80">
              {users.map((u) => (
                <div
                  key={u.username}
                  className="py-3 flex items-center justify-between gap-4 text-xs"
                >
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-slate-800 flex items-center justify-center font-bold text-slate-300">
                      {u.username.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div className="font-semibold text-white">{u.username}</div>
                      <div className="text-[10px] text-slate-400">
                        {u.username === currentUser?.username ? '(Current User)' : 'Standard Account'}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                        u.role === 'admin'
                          ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                          : 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                      }`}
                    >
                      {u.role.toUpperCase()}
                    </span>

                    {u.username !== currentUser?.username && (
                      <button
                        onClick={() => handleRoleToggle(u.username, u.role)}
                        className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-750 text-slate-300 border border-slate-700 transition"
                      >
                        Make {u.role === 'admin' ? 'User' : 'Admin'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Create User Card */}
        <div className="rounded-2xl bg-slate-900 border border-slate-800 p-5 space-y-4 shadow-lg h-fit">
          <div className="flex items-center gap-2 font-semibold text-sm text-white">
            <UserPlus className="h-4 w-4 text-indigo-400" />
            <span>Create New User</span>
          </div>

          <form onSubmit={handleCreateUser} className="space-y-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Username</label>
              <input
                type="text"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                placeholder="e.g. jane_doe"
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Min 8 characters"
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Role</label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-indigo-500"
              >
                <option value="user">User (Standard Access)</option>
                <option value="admin">Administrator (Full Access)</option>
                <option value="manager">Manager</option>
              </select>
            </div>
            <button
              type="submit"
              disabled={creating}
              className="w-full py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white shadow-md shadow-indigo-600/30 transition disabled:opacity-50"
            >
              {creating ? 'Creating…' : 'Create User Account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
