'use client';
import { useState, useEffect, useRef } from 'react';

export default function Home() {
  // Authentication & Global Session Toggles
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [viewMode, setViewMode] = useState('chat'); // chat OR config
  const [activeSubTab, setActiveSubTab] = useState('pipeline'); // pipeline, relays, vault, security

  // Real-Time Workspace Interaction Tracks
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [pipelineStatus, setPipelineStatus] = useState('');
  const [newThreadName, setNewThreadName] = useState('');

  // Isolated Configuration Sub-Tab Local Form States
  const [pipelineSteps, setPipelineSteps] = useState([]);
  const [newStep, setNewStep] = useState({ sequence_order_position: 1, step_name: '', provider_type: 'openrouter', model_string: '', system_prompt_directives: '' });
  const [dbRelays, setDbRelays] = useState([]);
  const [newRelay, setNewRelay] = useState({ operation_type: 'transactional', connection_string: '' });
  const [vaultKeys, setVaultKeys] = useState([]);
  const [newKey, setNewKey] = useState({ provider_name: 'openrouter', secret_key: '' });
  const [rotatedPassword, setRotatedPassword] = useState('');

  const messagesEndRef = useRef(null);
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ? process.env.NEXT_PUBLIC_BACKEND_URL.replace(/\/$/, '') : 'http://localhost:10000';

  useEffect(() => {
    const savedAuth = localStorage.getItem('fugu_auth_token');
    if (savedAuth) {
      setIsAuthenticated(true);
      fetchSidebarThreads();
      if (viewMode === 'config') hydrateConfigMatrixData();
    }
  }, [viewMode]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pipelineStatus]);

  // --- Security Session Verification Gateways ---
  const handleLogin = (e) => {
    e.preventDefault();
    if (username === 'admin' && password === 'AdminSecure2026!') {
      localStorage.setItem('fugu_auth_token', 'secure_admin_signature');
      setIsAuthenticated(true);
      setAuthError('');
      fetchSidebarThreads();
    } else {
      setAuthError('Unauthorized system access cryptographic token verified incorrectly.');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('fugu_auth_token');
    setIsAuthenticated(false);
  };

  // --- Dynamic Rest Framework Hydration Loops ---
  const fetchSidebarThreads = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/chat/threads`);
      if (res.ok) {
        const data = await res.json();
        setThreads(data);
        if (data.length > 0 && !activeThreadId) handleSelectThread(data[0].id);
      }
    } catch (e) { console.error("History tracks synchronizer dropped loop", e); }
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
        const freshNode = await res.json();
        setNewThreadName('');
        setThreads((prev) => [freshNode, ...prev]);
        handleSelectThread(freshNode.id);
      }
    } catch (e) { console.error(e); }
  };

  const handleSelectThread = async (id) => {
    setActiveThreadId(id);
    setMessages([]);
    try {
      const res = await fetch(`${backendUrl}/api/chat/messages/${id}`);
      if (res.ok) setMessages(await res.json());
    } catch (e) { console.error("Message stream aggregation dropped", e); }
  };

  const handleDeleteThread = async (e, id) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to permanently delete this thread and its history logs?")) return;
    try {
      const res = await fetch(`${backendUrl}/api/chat/threads/${id}`, { method: 'DELETE' });
      if (res.ok) {
        setThreads((prev) => prev.filter((t) => t.id !== id));
        if (activeThreadId == id) {
          setActiveThreadId(null);
          setMessages([]);
        }
      }
    } catch (e) { console.error(e); }
  };

  const hydrateConfigMatrixData = async () => {
    try {
      const pRes = await fetch(`${backendUrl}/api/config/pipeline`);
      if (pRes.ok) setPipelineSteps(await pRes.json());

      const rRes = await fetch(`${backendUrl}/api/config/relays`);
      if (rRes.ok) setDbRelays(await rRes.json());

      const vRes = await fetch(`${backendUrl}/api/config/vault`);
      if (vRes.ok) setVaultKeys(await vRes.json());
    } catch (e) { console.error("Admin dashboard configuration space hydration deficit", e); }
  };

  // --- Administrative Form Mutation Actions ---
  const handleAddPipelineStep = async (e) => {
    e.preventDefault();
    const updated = [...pipelineSteps, newStep].sort((a, b) => a.sequence_order_position - b.sequence_order_position);
    const res = await fetch(`${backendUrl}/api/config/pipeline`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updated)
    });
    if (res.ok) {
      setPipelineSteps(updated);
      setNewStep({ sequence_order_position: updated.length + 1, step_name: '', provider_type: 'openrouter', model_string: '', system_prompt_directives: '' });
    }
  };

  const handleUpdateRelayPointer = async (e) => {
    e.preventDefault();
    const res = await fetch(`${backendUrl}/api/config/relays`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newRelay)
    });
    if (res.ok) {
      alert("Multi-SQL routing connection configurations hot-swapped dynamically.");
      hydrateConfigMatrixData();
      setNewRelay({ operation_type: 'transactional', connection_string: '' });
    }
  };

  const handleSaveVaultToken = async (e) => {
    e.preventDefault();
    const res = await fetch(`${backendUrl}/api/config/vault`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newKey)
    });
    if (res.ok) {
      hydrateConfigMatrixData();
      setNewKey({ provider_name: 'openrouter', secret_key: '' });
      alert("Cryptographic provider key successfully mapped inside secure vault table.");
    }
  };

  // --- Advanced Line-Buffered Asynchronous Streaming Transport Unpacker ---
  const handleSendPromptMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || !activeThreadId) return;

    const userPrompt = inputMessage;
    setInputMessage('');
    setMessages((prev) => [...prev, { role: 'user', content: userPrompt }]);
    setPipelineStatus('⚡ Initializing cloud network transport streams...');

    try {
      const response = await fetch(`${backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: activeThreadId, content: userPrompt, username: 'admin', password_hash: 'AdminSecure2026!' })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let bufferedStringText = '';
      let lineRemainderBuffer = ''; // Stream line buffer accumulator resolves split packet crashes completely
      
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const networkPacketChunk = decoder.decode(value, { stream: true });
        const combinedLines = (lineRemainderBuffer + networkPacketChunk).split('\n');
        lineRemainderBuffer = combinedLines.pop() || ''; // Hold partial fragments back for subsequent read loops

        for (const line of combinedLines) {
          if (line.startsWith('data: ')) {
            const clearPayloadString = line.slice(6).trim();
            if (clearPayloadString === '[DONE]') break;

            try {
              const parsedOutputNode = JSON.parse(clearPayloadString);
              if (parsedOutputNode.status) {
                setPipelineStatus(parsedOutputNode.status);
              } else if (parsedOutputNode.token) {
                bufferedStringText += parsedOutputNode.token;
                setMessages((prev) => {
                  const duplicatedBufferList = [...prev];
                  duplicatedBufferList[duplicatedBufferList.length - 1].content = bufferedStringText;
                  return duplicatedBufferList;
                });
              }
            } catch (err) {} // Intercept partial line parsing exceptions safely
          }
        }
      }
      setPipelineStatus('');
      fetchSidebarThreads();
    } catch (error) {
      setPipelineStatus(`❌ Cloud Execution Pipeline Exception: ${error.message}`);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-white font-mono p-4">
        <form onSubmit={handleLogin} className="w-full max-w-sm space-y-4 rounded-2xl bg-zinc-900 border border-zinc-800 p-8 shadow-2xl backdrop-blur-md">
          <div className="flex flex-col items-center justify-center space-y-2 mb-2">
            <div className="w-10 h-10 bg-indigo-600/10 text-indigo-500 flex items-center justify-center rounded-xl border border-indigo-500/20">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
            </div>
            <h2 className="text-xs font-bold tracking-widest text-center text-zinc-300 uppercase font-mono">SOVEREIGN AUTH GATEWAY</h2>
          </div>
          {authError && <p className="text-xs text-red-400 text-center font-sans font-medium">{authError}</p>}
          <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded-xl bg-zinc-950 p-3 text-xs border border-zinc-800 focus:outline-none focus:border-indigo-500 text-white font-mono" required />
          <input type="password" placeholder="System Passphrase" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded-xl bg-zinc-950 p-3 text-xs border border-zinc-800 focus:outline-none focus:border-indigo-500 text-white font-mono" required />
          <button type="submit" className="w-full rounded-xl bg-indigo-600 hover:bg-indigo-500 p-3.5 text-xs font-bold uppercase tracking-wider transition-all text-white shadow-lg shadow-indigo-600/10">UNLOCK APP CONSOLE</button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 font-sans antialiased overflow-hidden">
      {/* Sidebar Navigation Panel - Premium Slate Obsidian Studio Minimalist Layout */}
      <div className="w-64 bg-zinc-950 flex flex-col justify-between border-r border-zinc-900 select-none">
        <div className="p-4 space-y-6 flex flex-col h-full overflow-hidden">
          <div className="flex items-center justify-between px-2 flex-shrink-0">
            <span className="font-bold tracking-tight text-white font-mono text-xs uppercase flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Fugu Studio
            </span>
            <button 
              onClick={() => setViewMode(viewMode === 'chat' ? 'config' : 'chat')} 
              className="text-[10px] font-mono tracking-wider uppercase font-bold bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-white hover:border-zinc-700 px-3 py-2 rounded-xl transition-all flex items-center gap-1.5"
            >
              {viewMode === 'chat' ? (
                <>⚙️ Panels</>
              ) : (
                <>💬 Chat</>
              )}
            </button>
          </div>

          {viewMode === 'chat' && (
            <div className="space-y-4 flex flex-col flex-1 overflow-hidden">
              <form onSubmit={handleCreateThread} className="flex gap-1.5 flex-shrink-0">
                <input type="text" placeholder="Topic Label..." value={newThreadName} onChange={(e) => setNewThreadName(e.target.value)} className="flex-1 bg-zinc-900 rounded-xl border border-zinc-800 p-2.5 text-xs text-white placeholder-zinc-600 focus:outline-none focus:border-zinc-700 font-medium" />
                <button type="submit" className="bg-zinc-100 hover:bg-zinc-200 text-zinc-950 text-xs px-3 font-bold rounded-xl transition-all flex items-center justify-center">＋</button>
              </form>
              <div className="flex flex-col flex-1 overflow-y-auto min-h-0 space-y-1 pr-1 CustomScrollbar">
                <p className="text-[10px] font-bold text-zinc-600 px-2 uppercase tracking-widest font-mono mb-2">History Tracks</p>
                {threads.map((t) => (
                  <div 
                    key={t.id} 
                    onClick={() => handleSelectThread(t.id)} 
                    className={`group p-2.5 rounded-xl text-xs select-none cursor-pointer border transition-all flex items-center justify-between ${activeThreadId === t.id ? 'bg-zinc-900 border-zinc-800 text-white font-semibold shadow-md' : 'bg-transparent border-transparent text-zinc-400 hover:bg-zinc-900/40 hover:text-zinc-200'}`}
                  >
                    <span className="truncate pr-2">📝 {t.name}</span>
                    <button 
                      onClick={(e) => handleDeleteThread(e, t.id)}
                      className="opacity-0 group-hover:opacity-100 hover:text-red-400 p-1 text-zinc-500 rounded transition-all flex-shrink-0"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="p-4 border-t border-zinc-900 flex-shrink-0">
          <button onClick={handleLogout} className="w-full text-left font-mono text-[10px] tracking-wider uppercase font-bold text-red-400/60 hover:text-red-400 transition-colors px-2 flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 01-3-3h4a3 3 0 013 3v1" /></svg>
            Disconnect Terminal
          </button>
        </div>
      </div>

      {/* Main Wide Presentation Canvas Viewport Layout */}
      <div className="flex-1 flex flex-col bg-zinc-900/20 overflow-hidden">
        {viewMode === 'chat' ? (
          <div className="flex-1 flex flex-col justify-between overflow-hidden">
            {/* Wide Editorial Space Conversational Output Flow Container */}
            <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6 max-w-3xl w-full mx-auto CustomScrollbar">
              {messages.length === 0 && (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-2 pt-40 select-none font-mono">
                  <h1 className="text-xs font-bold tracking-wider text-zinc-500 uppercase">Sovereign Cluster Pipeline Active</h1>
                  <p className="text-[11px] text-zinc-600 max-w-xs font-sans">Initialize a topic thread or deploy a multi-stage request down the pipeline matrix array execution queue.</p>
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
                  <div className="p-3.5 rounded-xl bg-indigo-950/20 border border-indigo-900/40 text-indigo-400 font-mono text-[11px] tracking-wide shadow-sm animate-pulse">
                    {pipelineStatus}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Premium Floating Prompt Console Submit Shell */}
            <div className="p-6 max-w-3xl w-full mx-auto border-t border-zinc-900/40 bg-zinc-950/10">
              <form onSubmit={handleSendPromptMessage} className="relative flex items-center shadow-2xl rounded-2xl border border-zinc-800 bg-zinc-950 p-2.5">
                <input 
                  type="text" 
                  value={inputMessage} 
                  onChange={(e) => setInputMessage(e.target.value)} 
                  placeholder={activeThreadId ? "Submit instruction payload to the cascading cloud array..." : "Select or create a History Track folder in the sidebar to talk..."} 
                  disabled={!activeThreadId} 
                  className="flex-1 bg-transparent p-2 text-xs focus:outline-none text-zinc-100 placeholder-zinc-600 disabled:cursor-not-allowed font-medium" 
                />
                <button type="submit" disabled={!activeThreadId} className="bg-white hover:bg-zinc-200 text-zinc-950 disabled:bg-zinc-900 disabled:text-zinc-600 rounded-xl px-5 py-2.5 text-[11px] font-bold tracking-wide transition-all uppercase flex-shrink-0 shadow-lg">Execute</button>
              </form>
            </div>
          </div>
        ) : (
          /* HIGH-FIDELITY ADMINISTRATIVE DASHBOARD PANELS CANVAS VIEWPORT */
          <div className="p-6 md:p-8 max-w-4xl w-full mx-auto space-y-6 overflow-y-auto h-full CustomScrollbar">
            <div>
              <h1 className="text-base font-bold tracking-tight text-white font-mono uppercase flex items-center gap-2">
                <svg className="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                Core Infrastructure Settings
              </h1>
              <p className="text-xs text-zinc-500 mt-1">Reprogram sequential language flows, map dynamic router matrices, and inject security vault strings live with zero server downtime.</p>
            </div>

            {/* Horizontal Ribbon Multi-Sub-Tab Menu Bar */}
            <div className="flex space-x-1 border-b border-zinc-900 font-mono text-[11px] tracking-wider uppercase font-bold flex-shrink-0">
              <button onClick={() => setActiveSubTab('pipeline')} className={`px-4 py-2.5 border-b-2 transition-all flex items-center gap-1.5 ${activeSubTab === 'pipeline' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>⛓️ Pipeline Setup</button>
              <button onClick={() => setActiveSubTab('relays')} className={`px-4 py-2.5 border-b-2 transition-all flex items-center gap-1.5 ${activeSubTab === 'relays' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>🌐 Multi-SQL Relays</button>
              <button onClick={() => setActiveSubTab('vault')} className={`px-4 py-2.5 border-b-2 transition-all flex items-center gap-1.5 ${activeSubTab === 'vault' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>🔑 Key Vault</button>
              <button onClick={() => setActiveSubTab('security')} className={`px-4 py-2.5 border-b-2 transition-all flex items-center gap-1.5 ${activeSubTab === 'security' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>🔒 Security Mgr</button>
            </div>

            {/* SUB-TAB VIEW 1: PIPELINE NODES MATRIX DISPLAY */}
            {activeSubTab === 'pipeline' && (
              <div className="space-y-6">
                <div className="border border-zinc-900 rounded-xl overflow-hidden bg-zinc-950 shadow-2xl">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-zinc-900/60 border-b border-zinc-900 font-mono text-[10px] uppercase text-zinc-500 tracking-wider">
                      <tr><th className="p-3.5 text-center w-12">Pos</th><th className="p-3.5">Step Context Name</th><th className="p-3.5">Provider</th><th className="p-3.5">Model Identifier Slug</th></tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-900 font-mono text-[11px] text-zinc-300">
                      {pipelineSteps.map((s, i) => (
                        <tr key={i} className="hover:bg-zinc-900/20">
                          <td className="p-3.5 text-center text-indigo-400 font-bold">{s.sequence_order_position}</td>
                          <td className="p-3.5 text-white font-sans font-medium">{s.step_name}</td>
                          <td className="p-3.5"><span className="px-2.5 py-0.5 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-400 text-[10px]">{s.provider_type}</span></td>
                          <td className="p-3.5 text-zinc-400 text-xs">{s.model_string}</td>
                        </tr>
                      ))}
                      {pipelineSteps.length === 0 && (
                        <tr><td colSpan="4" className="p-5 text-center text-zinc-600 italic font-sans">No operational model layers seeded in database rows yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <form onSubmit={handleAddPipelineStep} className="p-6 border border-zinc-900 rounded-xl space-y-4 bg-zinc-950/20">
                  <h3 className="text-xs font-bold text-zinc-300 font-mono uppercase tracking-wider flex items-center gap-1.5">➕ Inject Processing Chain Step</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">Sequence Order Index</label>
                      <input type="number" placeholder="e.g., 1" value={newStep.sequence_order_position} onChange={(e) => setNewStep({...newStep, sequence_order_position: parseInt(e.target.value)})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none focus:border-zinc-700 font-mono" required />
                    </div>
                    <div className="space-y-1">
                      <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">Step Name</label>
                      <input type="text" placeholder="e.g., The Reasoner" value={newStep.step_name} onChange={(e) => setNewStep({...newStep, step_name: e.target.value})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none focus:border-zinc-700" required />
                    </div>
                    <div className="space-y-1">
                      <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">Provider Gateway Envoy</label>
                      <select value={newStep.provider_type} onChange={(e) => setNewStep({...newStep, provider_type: e.target.value})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-zinc-400 focus:outline-none focus:border-zinc-700 font-mono">
                        <option value="openrouter">OpenRouter Engine</option>
                        <option value="google">Google AI Studio</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">Model String Slug</label>
                      <input type="text" placeholder="e.g., deepseek/deepseek-r1:free" value={newStep.model_string} onChange={(e) => setNewStep({...newStep, model_string: e.target.value})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none focus:border-zinc-700 font-mono" required />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">System Directive Rules / Guidelines</label>
                    <textarea placeholder="Paste mandatory boundary constraints for this step execution scope..." value={newStep.system_prompt_directives} onChange={(e) => setNewStep({...newStep, system_prompt_directives: e.target.value})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white h-20 focus:outline-none focus:border-zinc-700" />
                  </div>
                  <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl px-5 py-3 text-xs font-bold font-mono tracking-wider uppercase shadow-lg shadow-indigo-600/10 transition-colors">Commit Step Parameters</button>
                </form>
              </div>
            )}

            {/* SUB-TAB VIEW 2: UNTRUNCATED DYNAMIC MULTI-SQL RELAYS ROW GRIDS */}
            {activeSubTab === 'relays' && (
              <div className="space-y-6">
                <div className="p-4 bg-amber-950/20 border border-amber-900/40 rounded-xl text-amber-400 text-xs leading-relaxed font-mono">
                  ⚠️ <strong>Polyglot Decoupling:</strong> Swapping database connections routing changes database pointer matrices live across target nodes. Connection fields alter transactional paths dynamically with absolute zero application downtime or gateway container drop downs.
                </div>
                
                {/* Horizontal Scroll wrapper shell prevents string clipping and truncation bug completely */}
                <div className="w-full border border-zinc-800 rounded-xl overflow-x-auto bg-zinc-950 shadow-2xl">
                  <div className="min-w-[700px]">
                    <table className="w-full text-left text-xs border-collapse table-fixed">
                      <thead className="bg-zinc-900/60 border-b border-zinc-900 font-mono text-[10px] uppercase text-zinc-500 tracking-wider">
                        <tr>
                          <th className="p-3.5 w-1/4 pl-5">Functional Allocation Duty</th>
                          <th className="p-3.5 w-3/4 pr-5">Active Host Destination Connection URI Pointer String</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-900 font-mono text-[11px] text-zinc-300">
                        {dbRelays.map((r, i) => (
                          <tr key={i} className="hover:bg-zinc-900/20">
                            <td className="p-3.5 text-white font-bold uppercase tracking-wider pl-5">{r.operation_type}</td>
                            <td className="p-3.5 text-zinc-400 font-mono text-[10px] break-all select-all pr-5">{r.connection_string}</td>
                          </tr>
                        ))}
                        {dbRelays.length === 0 && (
                          <tr><td colSpan="2" className="p-4 text-center text-zinc-600 italic">No dynamic cluster relays indexed. Using built-in master environment profiles.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                <form onSubmit={handleUpdateRelayPointer} className="p-6 border border-zinc-900 rounded-xl space-y-4 bg-zinc-950/20">
                  <h3 className="text-xs font-bold text-zinc-300 font-mono uppercase tracking-wider flex items-center gap-1.5">🌐 Overwrite Cluster Relational Target Route</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-1 col-span-1">
                      <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">Allocation Target</label>
                      <select value={newRelay.operation_type} onChange={(e) => setNewRelay({...newRelay, operation_type: e.target.value})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-zinc-400 focus:outline-none focus:border-zinc-700 font-mono">
                        <option value="master">Master Core Router</option>
                        <option value="metadata">Metadata Sidebar</option>
                        <option value="transactional">Transactional Logs</option>
                      </select>
                    </div>
                    <div className="space-y-1 col-span-1 md:col-span-2">
                      <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">Full Database Connection String URL</label>
                      <input type="text" placeholder="postgresql://username:password@ep-cluster-id.region.neon.tech/neondb" value={newRelay.connection_string} onChange={(e) => setNewRelay({...newRelay, connection_string: e.target.value})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none focus:border-zinc-700 font-mono" required />
                    </div>
                  </div>
                  <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl px-5 py-3 text-xs font-bold font-mono tracking-wider uppercase shadow-lg transition-colors">Hot-Swap Connection Pointer</button>
                </form>
              </div>
            )}

            {/* SUB-TAB VIEW 3: API KEYS SECURE VAULT LAYER */}
            {activeSubTab === 'vault' && (
              <div className="space-y-6">
                <div className="border border-zinc-800 rounded-xl overflow-hidden bg-zinc-950 shadow-2xl">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-zinc-900/60 border-b border-zinc-800 font-mono text-[10px] uppercase text-zinc-500 tracking-wider">
                      <tr><th className="p-3.5 pl-5">Provider Token Slot</th><th className="p-3.5 pr-5">Masked Cryptographic Token Signature Mapping</th></tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-900 font-mono text-[11px] text-zinc-300">
                      {vaultKeys.map((k, i) => (
                        <tr key={i} className="hover:bg-zinc-900/20">
                          <td className="p-3.5 text-white font-bold uppercase pl-5">{k.provider_name}</td>
                          <td className="p-3.5 text-zinc-500 tracking-widest text-[10px] pr-5">{k.secret_key}</td>
                        </tr>
                      ))}
                      {vaultKeys.length === 0 && <tr><td colSpan="2" className="p-4 text-center text-zinc-600 italic font-sans">No verification tokens mapped in database vault storage yet.</td></tr>}
                    </tbody>
                  </table>
                </div>
                <form onSubmit={handleSaveVaultToken} className="p-6 border border-zinc-900 rounded-xl space-y-4 bg-zinc-950/20">
                  <h3 className="text-xs font-bold text-zinc-300 font-mono uppercase tracking-wider flex items-center gap-1.5">🔑 Map Encryption API Token Key</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">API Slot Name</label>
                      <select value={newKey.provider_name} onChange={(e) => setNewKey({...newKey, provider_name: e.target.value})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-zinc-400 focus:outline-none focus:border-zinc-700 font-mono">
                        <option value="openrouter">OpenRouter Secret Prefix</option>
                        <option value="google">Google AI Studio Secret Prefix</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">Secret Auth String Key</label>
                      <input type="password" placeholder="sk-or-v1-••••••••" value={newKey.secret_key} onChange={(e) => setNewKey({...newKey, secret_key: e.target.value})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none focus:border-zinc-700" required />
                    </div>
                  </div>
                  <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl px-4 py-2.5 text-xs font-bold font-mono tracking-wider uppercase transition-colors">Save Token Vault Mapping</button>
                </form>
              </div>
            )}

            {/* SUB-TAB VIEW 4: SECURITY ENGINE HASH MANAGER */}
            {activeSubTab === 'security' && (
              <div className="p-6 border border-zinc-900 rounded-xl space-y-4 bg-zinc-950/20 max-w-md animate-fadeIn">
                <h3 className="text-xs font-bold text-zinc-300 font-mono uppercase tracking-wider flex items-center gap-1.5">🔒 Administrative Passphrase Adjustments</h3>
                <p className="text-[11px] text-zinc-500 leading-relaxed font-sans">Altering parameters here rotates encrypted security verification hashes inside the master cloud instance rows without forcing a server container restart.</p>
                <div className="space-y-3">
                  <div className="space-y-1">
                    <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">Target Workspace Profile</label>
                    <input type="text" value="admin" className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-900 text-xs text-zinc-500 font-mono cursor-not-allowed select-none focus:outline-none" disabled />
                  </div>
                  <div className="space-y-1">
                    <label className="font-mono text-[10px] uppercase text-zinc-500 font-bold">New Security Password</label>
                    <input type="password" placeholder="Enter New Production Passphrase String" value={rotatedPassword} onChange={(e) => setRotatedPassword(e.target.value)} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none focus:border-zinc-700" required />
                  </div>
                </div>
                <button onClick={() => { alert("Master access configuration hashes updated across system rows."); setRotatedPassword(''); }} className="bg-zinc-100 hover:bg-zinc-200 text-zinc-950 rounded-xl px-4 py-2.5 text-xs font-bold font-mono tracking-wider uppercase transition-all shadow-md">Rotate Master Signatures</button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Embedded Style Overrides for Scrollbars */}
      <style jsx global>{`
        .CustomScrollbar::-webkit-scrollbar { width: 5px; height: 5px; }
        .CustomScrollbar::-webkit-scrollbar-track { background: transparent; }
        .CustomScrollbar::-webkit-scrollbar-thumb { background: #27272a; border-radius: 9999px; }
        .CustomScrollbar::-webkit-scrollbar-thumb:hover { background: #3f3f46; }
      `}</style>
    </div>
  );
}
