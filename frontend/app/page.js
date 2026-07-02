'use client';
import { useState, useEffect, useRef } from 'react';

export default function Home() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  
  const [viewMode, setViewMode] = useState('chat'); // chat OR settings
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [pipelineStatus, setPipelineStatus] = useState('');
  const [newThreadName, setNewThreadName] = useState('');
  
  const [pipelineSteps, setPipelineSteps] = useState([]);
  const [vaultKeys, setVaultKeys] = useState([]);
  const [newKey, setNewKey] = useState({ provider_name: 'openrouter', secret_key: '' });

  const messagesEndRef = useRef(null);
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ? process.env.NEXT_PUBLIC_BACKEND_URL.replace(/\/$/, '') : 'http://localhost:10000';

  useEffect(() => {
    const token = localStorage.getItem('fugu_session_token');
    if (token) {
      setIsAuthenticated(true);
      fetchThreads();
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated && viewMode === 'settings') {
      fetchAdminSettingsData();
    }
  }, [viewMode, isAuthenticated]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pipelineStatus]);

  const getHeaders = () => {
    const token = localStorage.getItem('fugu_session_token');
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    };
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError('');
    try {
      const res = await fetch(`${backendUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('fugu_session_token', data.token);
        setIsAuthenticated(true);
        fetchThreads();
      } else {
        setAuthError('Authentication rejected by access control service.');
      }
    } catch (err) {
      setAuthError('System interface connection error.');
      console.error('Login routing failure:', err);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('fugu_session_token');
    setIsAuthenticated(false);
  };

  const fetchThreads = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/chat/threads`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        setThreads(data);
        if (data.length > 0 && !activeThreadId) {
          handleSelectThread(data[0].id);
        }
      }
    } catch (e) { console.error('Thread log sync interrupt:', e); }
  };

  const handleCreateThread = async (e) => {
    e.preventDefault();
    if (!newThreadName.trim()) return;
    try {
      const res = await fetch(`${backendUrl}/api/chat/threads`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ name: newThreadName })
      });
      if (res.ok) {
        const data = await res.json();
        setNewThreadName('');
        setThreads((prev) => [data, ...prev]);
        handleSelectThread(data.id);
      }
    } catch (e) { console.error('Thread generation fault:', e); }
  };

  const handleSelectThread = async (id) => {
    setActiveThreadId(id);
    setMessages([]);
    try {
      const res = await fetch(`${backendUrl}/api/chat/messages/${id}`, { headers: getHeaders() });
      if (res.ok) setMessages(await res.json());
    } catch (e) { console.error('Message history parse failure:', e); }
  };

  const handleDeleteThread = async (e, id) => {
    e.stopPropagation();
    if (!confirm('Permanently purge this context matrix track?')) return;
    try {
      const res = await fetch(`${backendUrl}/api/chat/threads/${id}`, { 
        method: 'DELETE', 
        headers: getHeaders() 
      });
      if (res.ok) {
        setThreads((prev) => prev.filter((t) => t.id !== id));
        if (activeThreadId === id) {
          setActiveThreadId(null);
          setMessages([]);
        }
      }
    } catch (e) { console.error('Thread deletion fault:', e); }
  };

  const fetchAdminSettingsData = async () => {
    try {
      const pRes = await fetch(`${backendUrl}/api/config/pipeline`, { headers: getHeaders() });
      if (pRes.ok) setPipelineSteps(await pRes.pRes.json() || await pRes.json());

      const vRes = await fetch(`${backendUrl}/api/config/vault`, { headers: getHeaders() });
      if (vRes.ok) setVaultKeys(await vRes.json());
    } catch (e) { console.error('Hydration parsing exception:', e); }
  };

  const handleUpdateModelString = async (stepNum, fieldId) => {
    const inputEl = document.getElementById(fieldId);
    if (!inputEl) return;
    
    const updatedSteps = pipelineSteps.map((step) => {
      if (step.sequence_order_position === stepNum) {
        return { ...step, model_string: inputEl.value };
      }
      return step;
    });

    try {
      const res = await fetch(`${backendUrl}/api/config/pipeline`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(updatedSteps)
      });
      if (res.ok) {
        alert('Configuration synchronized.');
        fetchAdminSettingsData();
      }
    } catch (e) { console.error('Pipeline serialization fault:', e); }
  };

  const handleSaveVaultKey = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${backendUrl}/api/config/vault`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(newKey)
      });
      if (res.ok) {
        setNewKey({ provider_name: 'openrouter', secret_key: '' });
        alert('Vault parameters updated.');
        fetchAdminSettingsData();
      }
    } catch (e) { console.error('Vault persistence error:', e); }
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || !activeThreadId) return;

    const userPrompt = inputMessage;
    setInputMessage('');
    setMessages((prev) => [...prev, { role: 'user', content: userPrompt }]);
    setPipelineStatus('Transport link streaming active.');

    try {
      const response = await fetch(`${backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ thread_id: activeThreadId, content: userPrompt })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let streamText = '';
      let lineRemainderBuffer = '';

      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const networkChunk = decoder.decode(value, { stream: true });
        const combinedLines = (lineRemainderBuffer + networkChunk).split('\n');
        lineRemainderBuffer = combinedLines.pop() || '';

        for (const line of combinedLines) {
          if (line.startsWith('data: ')) {
            const cleanStr = line.slice(6).trim();
            if (cleanStr === '[DONE]') break;
            try {
              const parsed = JSON.parse(cleanStr);
              if (parsed.status) {
                setPipelineStatus(parsed.status);
              } else if (parsed.token) {
                streamText += parsed.token;
                setMessages((prev) => {
                  const updatedList = [...prev];
                  updatedList[updatedList.length - 1].content = streamText;
                  return updatedList;
                });
              }
            } catch (err) {
              print('SSE string breakdown encountered during text parse sequence:', err);
            }
          }
        }
      }
      setPipelineStatus('');
      fetchThreads();
    } catch (error) {
      setPipelineStatus(`Transport execution error: ${error.message}`);
      console.error('Asynchronous process error:', error);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-white font-mono p-4">
        <form onSubmit={handleLogin} className="w-full max-w-sm space-y-4 rounded-xl bg-zinc-900 border border-zinc-800 p-8 shadow-2xl">
          <h2 className="text-xs font-bold tracking-widest text-center uppercase text-zinc-400">Authentication Gateway</h2>
          {authError && <p className="text-xs text-red-400 text-center font-sans">{authError}</p>}
          <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded-xl bg-zinc-950 p-3 tenderness text-xs border border-zinc-800 focus:outline-none text-white font-mono" />
          <input type="password" placeholder="Passphrase" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded-xl bg-zinc-950 p-3 tenderness text-xs border border-zinc-800 focus:outline-none text-white font-mono" />
          <button type="submit" className="w-full rounded-xl bg-zinc-100 hover:bg-zinc-200 text-zinc-950 p-3.5 text-xs font-bold tracking-wider transition-all uppercase">Verify</button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 font-sans antialiased overflow-hidden">
      {/* Structural Workspace Sidebar Container */}
      <div className="w-64 bg-zinc-950 flex flex-col justify-between border-r border-zinc-900 select-none">
        <div className="p-4 space-y-6 flex flex-col h-full overflow-hidden">
          <div className="flex items-center justify-between px-1">
            <span className="font-bold tracking-tight text-white font-mono text-xs uppercase">
              Studio Environment
            </span>
            <button 
              onClick={() => setViewMode(viewMode === 'chat' ? 'settings' : 'chat')} 
              className="text-[10px] font-mono tracking-wider uppercase font-bold bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-white px-3 py-2 rounded-xl transition-all"
            >
              {viewMode === 'chat' ? 'Parameters' : 'Workspace'}
            </button>
          </div>

          {viewMode === 'chat' && (
            <div className="space-y-4 flex flex-col flex-1 overflow-hidden">
              <form onSubmit={handleCreateThread} className="flex gap-1.5">
                <input type="text" placeholder="New track label..." value={newThreadName} onChange={(e) => setNewThreadName(e.target.value)} className="flex-1 bg-zinc-900 rounded-xl border border-zinc-800 p-2.5 text-xs text-white placeholder-zinc-700 focus:outline-none font-medium" required />
                <button type="submit" className="bg-zinc-100 hover:bg-zinc-200 text-zinc-950 text-xs px-3 font-bold rounded-xl transition-all">+</button>
              </form>
              <div className="flex flex-col flex-1 overflow-y-auto space-y-1 pr-1 CustomScrollbar">
                <p className="text-[10px] font-bold text-zinc-600 px-2 uppercase tracking-widest font-mono mb-2">History Records</p>
                {threads.map((t) => (
                  <div 
                    key={t.id} 
                    onClick={() => handleSelectThread(t.id)} 
                    className={`group p-2.5 rounded-xl text-xs select-none cursor-pointer border transition-all flex items-center justify-between ${activeThreadId === t.id ? 'bg-zinc-900 border-zinc-800 text-white font-semibold' : 'bg-transparent border-transparent text-zinc-500 hover:text-zinc-300'}`}
                  >
                    <span className="truncate pr-2">{t.name}</span>
                    <button onClick={(e) => { e.stopPropagation(); handleDeleteThread(e, t.id); }} className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 font-bold transition-all px-1">
                      x
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="p-4 border-t border-zinc-900">
          <button onClick={handleLogout} className="w-full text-left font-mono text-[10px] tracking-wider uppercase font-bold text-zinc-600 hover:text-zinc-400 transition-colors px-2">
            Terminate Session
          </button>
        </div>
      </div>

      {/* Main Studio View Canvas Component */}
      <div className="flex-1 flex flex-col bg-zinc-900/10 overflow-hidden">
        {viewMode === 'chat' ? (
          <div className="flex-1 flex flex-col justify-between overflow-hidden">
            <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 max-w-3xl w-full mx-auto CustomScrollbar">
              {messages.length === 0 && (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-2 pt-40 select-none font-mono">
                  <h1 className="text-xs font-bold tracking-wider text-zinc-600 uppercase">Workspace Active</h1>
                  <p className="text-[11px] text-zinc-700 max-w-xs font-sans">Select or configure an execution context target within the workspace history tree options.</p>
                </div>
              )}
              {messages.map((m, idx) => (
                <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`p-4 rounded-2xl max-w-xl text-xs leading-relaxed border ${m.role === 'user' ? 'bg-zinc-900 border-zinc-800 text-zinc-200' : 'bg-zinc-950 border-zinc-900 text-zinc-100 shadow-2xl'}`}>
                    <p className="font-mono text-[9px] text-zinc-600 mb-1.5 uppercase tracking-widest font-bold">{m.role}</p>
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                </div>
              ))}
              {pipelineStatus && (
                <div className="flex justify-start">
                  <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-900 text-zinc-400 font-mono text-[11px] tracking-wide shadow-sm animate-pulse">
                    {pipelineStatus}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <div className="p-6 max-w-3xl w-full mx-auto border-t border-zinc-900/40 bg-zinc-950/10">
              <form onSubmit={sendMessage} className="relative flex items-center shadow-2xl rounded-2xl border border-zinc-800 bg-zinc-950 p-2.5">
                <input type="text" value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} placeholder={activeThreadId ? "Submit context instructions..." : "Select context history line item..."} disabled={!activeThreadId} className="flex-1 bg-transparent p-2 text-xs focus:outline-none text-zinc-100 placeholder-zinc-700 disabled:cursor-not-allowed font-medium" />
                <button type="submit" disabled={!activeThreadId} className="bg-white hover:bg-zinc-200 text-zinc-950 disabled:bg-zinc-900 disabled:text-zinc-700 rounded-xl px-5 py-2.5 text-[11px] font-bold tracking-wide transition-all uppercase flex-shrink-0">Send</button>
              </form>
            </div>
          </div>
        ) : (
          /* Consolidated Configuration Space Panels Matrix */
          <div className="p-6 md:p-8 max-w-3xl w-full mx-auto space-y-10 overflow-y-auto h-full CustomScrollbar">
            <div className="space-y-6">
              <div>
                <h1 className="text-sm font-bold tracking-tight text-white font-mono uppercase">Pipeline Node Sequences</h1>
                <p className="text-xs text-zinc-500 mt-1">Modify runtime model identifier blocks live within the database records space mappings.</p>
              </div>
              <div className="space-y-3">
                {pipelineSteps.map((step) => (
                  <div key={step.sequence_order_position} className="p-4 border border-zinc-900 rounded-xl bg-zinc-950 flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="space-y-0.5">
                      <h3 className="text-xs font-bold text-zinc-300 font-mono">Stage {step.sequence_order_position}: {step.step_name}</h3>
                      <p className="text-[9px] text-zinc-600 font-mono uppercase tracking-wider">Target Provider Type: {step.provider_type}</p>
                    </div>
                    <div className="flex gap-2 items-center w-full md:w-auto">
                      <input 
                        type="text" 
                        defaultValue={step.model_string} 
                        id={`model_field_input_${step.sequence_order_position}`}
                        className="p-2 border border-zinc-900 rounded-xl bg-zinc-900 text-xs text-zinc-400 font-mono focus:outline-none w-full md:w-52 text-right" 
                      />
                      <button 
                        onClick={() => handleUpdateModelString(step.sequence_order_position, `model_field_input_${step.sequence_order_position}`)} 
                        className="bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-[10px] font-mono border border-zinc-800 font-bold uppercase tracking-wider px-3.5 py-2 rounded-xl transition-all"
                      >
                        Save
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="border-t border-zinc-900 pt-6 space-y-6">
              <div>
                <h1 className="text-sm font-bold tracking-tight text-white font-mono uppercase">Key Vault Ingestion</h1>
                <p className="text-xs text-zinc-500 mt-1">Safely update verification tokens map credentials inside secure encrypted table fields.</p>
              </div>
              <form onSubmit={handleSaveVaultKey} className="p-4 border border-zinc-900 rounded-xl bg-zinc-950 flex items-center justify-between gap-4 flex-wrap md:flex-nowrap">
                <select value={newKey.provider_name} onChange={(e) => setNewKey({...newKey, provider_name: e.target.value})} className="p-2 border border-zinc-900 rounded-xl bg-zinc-900 text-xs text-zinc-400 font-mono focus:outline-none">
                  <option value="openrouter">openrouter</option>
                  <option value="google">google</option>
                </select>
                <input type="password" placeholder="Paste encryption credential token string..." value={newKey.secret_key} onChange={(e) => setNewKey({...newKey, secret_key: e.target.value})} className="p-2 border border-zinc-900 rounded-xl bg-zinc-900 text-xs text-white focus:outline-none flex-1 font-mono max-w-sm" required />
                <button type="submit" className="bg-zinc-100 hover:bg-zinc-200 text-zinc-950 text-[10px] font-mono font-bold uppercase tracking-wider px-4 py-2 rounded-xl transition-all">Persist Token</button>
              </form>
              <div className="rounded-xl border border-zinc-900 bg-zinc-950 overflow-hidden text-xs font-mono">
                {vaultKeys.map((k, idx) => (
                  <div key={idx} className="p-3 border-b border-zinc-900/60 flex justify-between items-center text-[11px]">
                    <span className="text-zinc-400 uppercase tracking-wider">{k.provider_name}</span>
                    <span className="text-zinc-600 tracking-widest">{k.secret_key}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      <style jsx global>{`
        .CustomScrollbar::-webkit-scrollbar { width: 4px; height: 4px; }
        .CustomScrollbar::-webkit-scrollbar-track { background: transparent; }
        .CustomScrollbar::-webkit-scrollbar-thumb { background: #18181b; border-radius: 9999px; }
        .CustomScrollbar::-webkit-scrollbar-thumb:hover { background: #27272a; }
      `}</style>
    </div>
  );
}
