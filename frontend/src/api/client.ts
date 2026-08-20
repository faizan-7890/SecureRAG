import type {
  ChatMessage,
  DocumentChunksResponse,
  DocumentRecord,
  RuntimeSettings,
  Source,
  TokenResponse,
  UserProfile,
} from '../types';

export class ApiClient {
  private settings: RuntimeSettings;
  private token: string | null;

  constructor(settings: RuntimeSettings, token: string | null) {
    this.settings = settings;
    this.token = token;
  }

  public update(settings: RuntimeSettings, token: string | null) {
    this.settings = settings;
    this.token = token;
  }

  private getHeaders(customHeaders: Record<string, string> = {}): Record<string, string> {
    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...customHeaders,
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const key = (this.settings.apiKey || '').trim();
    if (key) {
      if (key.startsWith('AIzaSy')) {
        headers['X-Gemini-API-Key'] = key;
      } else {
        headers['X-OpenAI-API-Key'] = key;
      }
    }

    return headers;
  }

  private getUrl(path: string): string {
    const base = (this.settings.apiUrl || 'http://127.0.0.1:8000').replace(/\/+$/, '');
    return `${base}${path.startsWith('/') ? path : `/${path}`}`;
  }

  public async getHealth(): Promise<{ status: string; latencyMs: number } | null> {
    const start = performance.now();
    try {
      const res = await fetch(this.getUrl('/health'), {
        headers: this.getHeaders(),
      });
      const latencyMs = Math.round(performance.now() - start);
      if (res.ok) {
        return { status: 'ok', latencyMs };
      }
      return null;
    } catch {
      return null;
    }
  }

  public async login(username: string, password: string): Promise<TokenResponse> {
    const res = await fetch(this.getUrl('/auth/login'), {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(err.detail || 'Login failed');
    }
    return res.json();
  }

  public async register(username: string, password: string): Promise<TokenResponse> {
    const res = await fetch(this.getUrl('/auth/register'), {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
      throw new Error(err.detail || 'Registration failed');
    }
    return res.json();
  }

  public async getMe(): Promise<UserProfile> {
    const res = await fetch(this.getUrl('/auth/me'), {
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      throw new Error('Failed to fetch user profile');
    }
    return res.json();
  }

  public async getUsers(): Promise<UserProfile[]> {
    const res = await fetch(this.getUrl('/auth/users'), {
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to fetch users' }));
      throw new Error(err.detail || 'Failed to fetch users');
    }
    const data = await res.json();
    return data.users || [];
  }

  public async updateUserRole(username: string, role: string): Promise<UserProfile> {
    const res = await fetch(this.getUrl(`/auth/users/${username}/role`), {
      method: 'PATCH',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ role }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to update role' }));
      throw new Error(err.detail || 'Failed to update role');
    }
    return res.json();
  }

  public async listDocuments(): Promise<DocumentRecord[]> {
    const res = await fetch(this.getUrl('/documents'), {
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      throw new Error('Failed to list documents');
    }
    const data = await res.json();
    return data.documents || [];
  }

  public async uploadDocument(file: File): Promise<{ filename: string; chunks: number; document_id: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: Record<string, string> = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const res = await fetch(this.getUrl('/documents/upload'), {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Document upload failed' }));
      throw new Error(err.detail || 'Upload failed');
    }
    return res.json();
  }

  public async deleteDocument(documentId: string): Promise<void> {
    const res = await fetch(this.getUrl(`/documents/${documentId}`), {
      method: 'DELETE',
      headers: this.getHeaders(),
    });
    if (!res.ok && res.status !== 204) {
      const err = await res.json().catch(() => ({ detail: 'Delete failed' }));
      throw new Error(err.detail || 'Failed to delete document');
    }
  }

  public async getDocumentChunks(documentId: string): Promise<DocumentChunksResponse> {
    const res = await fetch(this.getUrl(`/documents/${documentId}/chunks`), {
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to load chunks' }));
      throw new Error(err.detail || 'Failed to load chunks');
    }
    return res.json();
  }

  public async streamChat(
    question: string,
    history: ChatMessage[],
    sessionId: string,
    onToken: (token: string) => void,
    onSources: (sources: Source[]) => void,
    onError: (error: string) => void,
    onDone: () => void,
  ): Promise<void> {
    const payload = {
      question,
      history: history.map((h) => ({ role: h.role, content: h.content })),
      session_id: sessionId,
      hybrid_search: this.settings.hybridSearch,
      query_expansion: this.settings.queryExpansion,
    };

    const url = this.getUrl('/chat/stream');
    const headers = this.getHeaders({
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    });

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({ detail: 'Chat stream failed' }));
        onError(errJson.detail || 'Request failed');
        onDone();
        return;
      }

      if (!response.body) {
        onError('ReadableStream not supported');
        onDone();
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let currentEvent = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) {
            currentEvent = '';
            continue;
          }

          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.slice(6).trim();
          } else if (trimmed.startsWith('data:')) {
            const dataStr = trimmed.slice(5).trim();
            try {
              const data = JSON.parse(dataStr);
              if (currentEvent === 'sources' && data.sources) {
                onSources(data.sources);
              } else if (currentEvent === 'token' && data.token) {
                onToken(data.token);
              } else if (currentEvent === 'error' && data.error) {
                onError(data.error);
              } else if (currentEvent === 'done') {
                onDone();
                return;
              }
            } catch {
              // ignore parse errors on malformed lines
            }
          }
        }
      }

      onDone();
    } catch (err: any) {
      onError(err.message || 'Connection error');
      onDone();
    }
  }
}
