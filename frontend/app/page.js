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
  const messagesEndRef = useRef(null);
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ? process.env.NEXT_PUBLIC_BACKEND_URL.replace(/\/$/, '') : 'http://localhost:10000';

  useEffect(() => {
    const savedAuth = localStorage.getItem('fugu_auth');
    if (savedAuth) {
      setIsAuthenticated(true);
      fetchThreads();
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated && viewMode === 'settings') {
      fetchPipelineSettings();
    }
  }, [viewMode, isAuthenticated]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pipelineStatus]);

  const handleLogin = (e) => {
    e.preventDefault();
    if (username === 'admin' && password === 'AdminSecure2026!') {
      localStorage.setItem('fugu_auth', 'true');
      setIsAuthenticated(true);
      setAuthError('');
      fetchThreads();
    } else {
      setAuthError('Invalid credentials.');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('fugu_auth');
    setIsAuthenticated(false);
  };

  const fetchThreads = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/chat/threads`);
      if (res.ok) {
        const data = await res.json();
        setThreads(data);
        if (data.length > 0 && !activeThreadId) {
          handleSelectThread(data[0].id);
        }
      }
    } catch (e) { console.error(e); }
  };

  const handleCreateThread = async (e) => {
    e.preventDefault();
    if (!newThreadName.trim()) return;
    try {
      const res = await fetch(`${backendUrl}/api/chat/threads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newThreadName })
      });
      if (res.ok) {
        const data = await res.json();
        setNewThreadName('');
        setThreads((prev) => [data, ...prev]);
        handleSelectThread(data.id);
      }
    } catch (e) { console.error(e); }
  };

  const handleSelectThread = async (id) => {
    setActiveThreadId(id);
    setMessages([]);
    try {
      const res = await fetch(`${backendUrl}/api/chat/messages/${id}`);
      if (res.ok) setMessages(await res.json());
    } catch (e) { console.error(e); }
  };

  const handleDeleteThread = async (e, id) => {
    e.stopPropagation();
    if (!confirm("Delete this thread?")) return;
    try {
      const res = await fetch(`${backendUrl}/api/chat/threads/${id}`, { method: 'DELETE' });
      if (res.ok) {
        setThreads((prev) => prev.filter((t) => t.id !== id));
        if (activeThreadId === id) {
          setActiveThreadId(null);
          setMessages([]);
        }
      }
    } catch (e) { console.error(e); }
  };

  const fetchPipelineSettings = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/config/pipeline`);
      if (res.ok) setPipelineSteps(await res.json());
    } catch (e) { console.error(e); }
  };

  const handleUpdateModelString = async (stepNum, newSlug) => {
    try {
      const res = await fetch(`${backendUrl}/api/config/pipeline/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_num: stepNum, model_string: newSlug })
      });
      if (res.ok) {
        alert("Model configuration updated.");
        fetchPipelineSettings();
      }
    } catch (e) { console.error(e); }
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || !activeThreadId) return;

    const userPrompt = inputMessage;
    setInputMessage('');
    setMessages((prev) => [...prev, { role: 'user', content: userPrompt }]);
    setPipelineStatus('Streaming transport connection active...');

    try {
      const response = await fetch(`${backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
              if (parsed.status) setPipelineStatus(parsed.status);
              else if (parsed.token) {
                streamText += parsed.token;
                setMessages((prev) => {
                  const updatedList = [...prev];
                  updatedList[updatedList.length - 1].content = streamText;
                  return updatedList;
                });
              }
            } catch (err) {}
          }
        }
      }
      setPipelineStatus('');
      fetchThreads();
    } catch (error) {
      setPipelineStatus(`Error: {error.message}`);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-white font-mono p-4">
        <form onSubmit={handleLogin} className="w-full max-w-sm space-y-4 rounded-xl bg-zinc-900 border border-zinc-800 p-8 shadow-2xl">
          <h2 className="text-xs font-bold tracking-widest text-center uppercase">System Authentication</h2>
          {authError && <p className="text-xs text-red-400 text-center font-sans font-medium">{authError}</p>}
          <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded-xl bg-zinc-950 p-3 text-xs border border-zinc-800 focus:outline-none focus:border-zinc-700 text-white" />
          <input type="password" placeholder="Passphrase" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded-xl bg-zinc-950 p-3 text-xs border border-zinc-800 focus:outline-none focus:border-zinc-700 text-white" />
          <button type="submit" className="w-full rounded-xl bg-zinc-100 hover:bg-zinc-200 text-zinc-950 p-3.5 text-xs font-bold tracking-wider transition-all uppercase">Login</button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 font-sans antialiased overflow-hidden">
      {/* Navigation panel layout */}
      <div className="w-64 bg-zinc-950 flex flex-col justify-between border-r border-zinc-900 select-none">
        <div className="p-4 space-y-6 flex flex-col h-full overflow-hidden">
          <div className="flex items-center justify-between px-1">
            <span className="font-bold tracking-tight text-white font-mono text-xs uppercase flex items-center gap-2">
              System Matrix
            </span>
            <button 
              onClick={() => setViewMode(viewMode === 'chat' ? 'settings' : 'chat')} 
              className="text-[10px] font-mono tracking-wider uppercase font-bold bg-zinc-900 border border-zinc-800 text-zinc-300 hover:text-white hover:border-zinc-700 px-3 py-2 rounded-xl transition-all"
            >
              {viewMode === 'chat' ? 'Models' : 'Chat'}
            </button>
          </div>

          {viewMode === 'chat' && (
            <div className="space-y-4 flex flex-col flex-1 overflow-hidden">
              <form onSubmit={handleCreateThread} className="flex gap-1.5">
                <input type="text" placeholder="New thread name..." value={newThreadName} onChange={(e) => setNewThreadName(e.target.value)} className="flex-1 bg-zinc-900 rounded-xl border border-zinc-800 p-2.5 text-xs text-white placeholder-zinc-600 focus:outline-none focus:border-zinc-700 font-medium" required />
                <button type="submit" className="bg-zinc-100 hover:bg-zinc-200 text-zinc-950 text-xs px-3 font-bold rounded-xl transition-all">+</button>
              </form>
              <div className="flex flex-col flex-1 overflow-y-auto space-y-1 pr-1 CustomScrollbar">
                <p className="text-[10px] font-bold text-zinc-600 px-2 uppercase tracking-widest font-mono mb-2">History</p>
                {threads.map((t) => (
                  <div 
                    key={t.id} 
                    onClick={() => handleSelectThread(t.id)} 
                    className={`group p-2.5 rounded-xl text-xs select-none cursor-pointer border transition-all flex items-center justify-between ${activeThreadId === t.id ? 'bg-zinc-900 border-zinc-800 text-white font-semibold shadow-md' : 'bg-transparent border-transparent text-zinc-400 hover:bg-zinc-900/40 hover:text-zinc-200'}`}
                  >
                    <span className="truncate pr-2">{t.name}</span>
                    <button onClick={(e) => { e.stopPropagation(); handleDeleteThread(e, t.id); }} className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 font-bold transition-all px-1">
                      x
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="p-4 border-t border-zinc-900">
          <button onClick={handleLogout} className="w-full text-left font-mono text-[10px] tracking-wider uppercase font-bold text-zinc-500 hover:text-zinc-300 transition-colors px-2">
            Logout
          </button>
        </div>
      </div>

      {/* Main workspace container view */}
      <div className="flex-1 flex flex-col bg-zinc-900/20 overflow-hidden">
        {viewMode === 'chat' ? (
          <div className="flex-1 flex flex-col justify-between overflow-hidden">
            {/* Conversation view content flow */}
            <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 max-w-3xl w-full mx-auto CustomScrollbar">
              {messages.length === 0 && (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-2 pt-40 select-none font-mono">
                  <h1 className="text-xs font-bold tracking-wider text-zinc-500 uppercase">System Active</h1>
                  <p className="text-[11px] text-zinc-600 max-w-xs font-sans">Select or create a thread on the sidebar to begin.</p>
                </div>
              )}
              {messages.map((m, idx) => (
                <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`p-4 rounded-2xl max-w-xl text-xs leading-relaxed border ${m.role === 'user' ? 'bg-zinc-900 border-zinc-800 text-zinc-200' : 'bg-zinc-950 border-zinc-900 text-zinc-100 shadow-2xl'}`}>
                    <p className="font-mono text-[9px] text-zinc-500 mb-1.5 uppercase tracking-widest font-bold">{m.role}</p>
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                </div>
              ))}
              {pipelineStatus && (
                <div className="flex justify-start">
                  <div className="p-3.5 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-400 font-mono text-[11px] tracking-wide shadow-sm animate-pulse">
                    {pipelineStatus}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input submission box interface */}
            <div className="p-6 max-w-3xl w-full mx-auto border-t border-zinc-900/40 bg-zinc-950/10">
              <form onSubmit={sendMessage} className="relative flex items-center shadow-2xl rounded-2xl border border-zinc-800 bg-zinc-950 p-2.5">
                <input type="text" value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} placeholder={activeThreadId ? "Send a message..." : "Select or create a thread to chat..."} disabled={!activeThreadId} className="flex-1 bg-transparent p-2 text-xs focus:outline-none text-zinc-100 placeholder-zinc-600 disabled:cursor-not-allowed font-medium" />
                <button type="submit" disabled={!activeThreadId} className="bg-white hover:bg-zinc-200 text-zinc-950 disabled:bg-zinc-900 disabled:text-zinc-600 rounded-xl px-5 py-2.5 text-[11px] font-bold tracking-wide transition-all uppercase flex-shrink-0">Send</button>
              </form>
            </div>
          </div>
        ) : (
          /* Consolidated configuration profile interface */
          <div className="p-6 md:p-8 max-w-4xl w-full mx-auto space-y-6 overflow-y-auto h-full CustomScrollbar">
            <div>
              <h1 className="text-base font-bold tracking-tight text-white font-mono uppercase">Model Configurations</h1>
              <p className="text-xs text-zinc-500 mt-1">Modify your backend deployment identifiers down below.</p>
            </div>

            <div className="space-y-4 pt-2">
              {pipelineSteps.map((step) => (
                <div key={step.step_num} className="p-5 border border-zinc-800 rounded-xl bg-zinc-950 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xl">
                  <div className="space-y-0.5">
                    <h3 className="text-xs font-bold text-zinc-200 font-mono">{step.step_name}</h3>
                    <p className="text-[10px] text-zinc-600 font-mono uppercase tracking-wider">Active model string</p>
                  </div>
                  <div className="flex gap-2 items-center w-full md:w-auto">
                    <input 
                      type="text" 
                      defaultValue={step.model_string} 
                      id={`model_input_${step.step_num}`}
                      className="p-2.5 border border-zinc-900 rounded-xl bg-zinc-900 text-xs text-zinc-300 font-mono focus:outline-none focus:border-zinc-700 flex-1 md:w-56" 
                    />
                    <button 
                      onClick={() => {
                        const inputEl = document.getElementById(`model_input_${step.step_num}`);
                        if (inputEl) handleUpdateModelString(step.step_num, inputEl.value);
                      }} 
                      className="bg-zinc-100 hover:bg-zinc-200 text-zinc-950 text-[10px] font-mono font-bold uppercase tracking-wider px-3.5 py-2.5 rounded-xl transition-colors flex-shrink-0"
                    >
                      Save
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <style jsx global>{`
        .CustomScrollbar::-webkit-scrollbar { width: 4px; height: 4px; }
        .CustomScrollbar::-webkit-scrollbar-track { background: transparent; }
        .CustomScrollbar::-webkit-scrollbar-thumb { background: #27272a; border-radius: 9999px; }
        .CustomScrollbar::-webkit-scrollbar-thumb:hover { background: #3f3f46; }
      `}</style>
    </div>
  );
}
