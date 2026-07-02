'use client';
import { useState, useEffect, useRef } from 'react';

export default function Home() {
  // Authentication & Global Layout Router States
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [viewMode, setViewMode] = useState('chat'); // chat OR config
  const [activeSubTab, setActiveSubTab] = useState('pipeline'); // pipeline, relays, vault, security

  // Interaction Logging Context States
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [pipelineStatus, setPipelineStatus] = useState('');

  // Isolated Configuration Sub-Tab Target States
  const [pipelineSteps, setPipelineSteps] = useState([]);
  const [newStep, setNewStep] = useState({ sequence_order_position: 1, step_name: '', provider_type: 'openrouter', model_string: '', system_prompt_directives: '' });
  
  const [dbRelays, setDbRelays] = useState([]);
  const [newRelay, setNewRelay] = useState({ operation_type: 'transactional', connection_string: '' });
  
  const [vaultKeys, setVaultKeys] = useState([]);
  const [newKey, setNewKey] = useState({ provider_name: 'openrouter', secret_key: '' });
  
  const [rotatedPassword, setRotatedPassword] = useState('');

  const messagesEndRef = useRef(null);
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:10000';

  useEffect(() => {
    const savedAuth = localStorage.getItem('fugu_auth_token');
    if (savedAuth) {
      setIsAuthenticated(true);
      hydrateApplicationMatrix();
    }
  }, [viewMode]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pipelineStatus]);

  const handleLogin = (e) => {
    e.preventDefault();
    if (username === 'admin' && password === 'AdminSecure2026!') {
      localStorage.setItem('fugu_auth_token', 'secure_admin_signature');
      setIsAuthenticated(true);
      setAuthError('');
      hydrateApplicationMatrix();
    } else {
      setAuthError('Invalid system access cryptographic signature token.');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('fugu_auth_token');
    setIsAuthenticated(false);
  };

  const hydrateApplicationMatrix = async () => {
    // Populate layout tracking properties
    setThreads([{ id: 1, name: 'Sovereign Core Live Track' }]);
    setActiveThreadId(1);
    
    try {
      const pRes = await fetch(`${backendUrl}/api/config/pipeline`);
      if (pRes.ok) setPipelineSteps(await pRes.json());
      
      const rRes = await fetch(`${backendUrl}/api/config/relays`);
      if (rRes.ok) setDbRelays(await rRes.json());

      const vRes = await fetch(`${backendUrl}/api/config/vault`);
      if (vRes.ok) setVaultKeys(await vRes.json());
    } catch (err) { console.error("Decoupled data hydration cycle interrupted", err); }
  };

  // --- Sub-Tab Mutation Submission Rules ---
  const handleAddStep = async (e) => {
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

  const handleUpdateRelay = async (e) => {
    e.preventDefault();
    const res = await fetch(`${backendUrl}/api/config/relays`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newRelay)
    });
    if (res.ok) {
      alert("Multi-SQL routing connection pointers swapped live with zero system downtime.");
      hydrateApplicationMatrix();
      setNewRelay({ operation_type: 'transactional', connection_string: '' });
    }
  };

  const handleSaveVaultKey = async (e) => {
    e.preventDefault();
    const res = await fetch(`${backendUrl}/api/config/vault`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newKey)
    });
    if (res.ok) {
      hydrateApplicationMatrix();
      setNewKey({ provider_name: 'openrouter', secret_key: '' });
      alert("Secret credential encapsulated successfully into cloud database vault storage.");
    }
  };

  const handleRotateSystemPassword = async (e) => {
    e.preventDefault();
    const res = await fetch(`${backendUrl}/api/config/security`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', new_password_hash: rotatedPassword })
    });
    if (res.ok) {
      alert("Master access passphrase token updated.");
      setRotatedPassword('');
    }
  };

  // --- Real-Time SSE Client Stream Unpack ---
  const sendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || !activeThreadId) return;

    const userPrompt = inputMessage;
    setInputMessage('');
    setMessages((prev) => [...prev, { role: 'user', content: userPrompt }]);
    setPipelineStatus('⚡ Activating secure cloud network transport streams...');

    try {
      const response = await fetch(`${backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thread_id: activeThreadId,
          content: userPrompt,
          username: 'admin',
          password_hash: 'AdminSecure2026!'
        })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let streamBufferText = '';
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const packetChunk = decoder.decode(value);
        const lines = packetChunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const cleanStr = line.slice(6).trim();
            if (cleanStr === '[DONE]') break;

            try {
              const parsedJson = JSON.parse(cleanStr);
              if (parsedJson.status) {
                setPipelineStatus(parsedJson.status);
              } else if (parsedJson.token) {
                streamBufferText += parsedJson.token;
                setMessages((prev) => {
                  const cloned = [...prev];
                  cloned[cloned.length - 1].content = streamBufferText;
                  return cloned;
                });
              }
            } catch (err) {}
          }
        }
      }
      setPipelineStatus('');
    } catch (error) {
      setPipelineStatus(`❌ Stream Error: ${error.message}`);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-white font-mono">
        <form onSubmit={handleLogin} className="w-85 space-y-4 rounded-2xl bg-zinc-900 border border-zinc-800 p-7 shadow-2xl">
          <h2 className="text-sm font-bold tracking-widest text-center text-zinc-200 uppercase">🔒 SOVEREIGN AUTH GATEWAY</h2>
          {authError && <p className="text-xs text-red-400 text-center">{authError}</p>}
          <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded-xl bg-zinc-950 p-3 text-xs border border-zinc-800 focus:outline-none focus:border-indigo-500 text-white" />
          <input type="password" placeholder="Passphrase" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded-xl bg-zinc-950 p-3 text-xs border border-zinc-800 focus:outline-none focus:border-indigo-500 text-white" />
          <button type="submit" className="w-full rounded-xl bg-indigo-600 p-3 text-xs font-bold uppercase tracking-wider hover:bg-indigo-500 transition-colors">UNLOCK MATRIX</button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 font-sans antialiased overflow-hidden">
      {/* Sidebar Navigation - Studio Dark Profile */}
      <div className="w-64 bg-zinc-950 flex flex-col justify-between border-r border-zinc-900 select-none">
        <div className="p-4 space-y-6">
          <div className="flex items-center justify-between px-2">
            <span className="font-bold tracking-tight text-white font-mono text-sm uppercase">🎨 FUGU MATRIX</span>
            <button 
              onClick={() => setViewMode(viewMode === 'chat' ? 'config' : 'chat')} 
              className="text-[10px] font-mono tracking-wider uppercase font-bold bg-zinc-900 border border-zinc-800 text-zinc-300 hover:text-white hover:border-zinc-700 px-3 py-2 rounded-xl transition-all"
            >
              {viewMode === 'chat' ? '⚙️ Control Panel' : '💬 Return To Chat'}
            </button>
          </div>
          {viewMode === 'chat' && (
            <div className="space-y-2">
              <p className="text-[10px] font-bold text-zinc-600 px-2 uppercase tracking-widest font-mono">Infrastructure Logs</p>
              {threads.map((t) => (
                <div key={t.id} className="p-3 rounded-xl text-xs text-zinc-300 bg-zinc-900 border border-zinc-900 cursor-pointer select-none">
                  📝 {t.name}
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="p-4 border-t border-zinc-900">
          <button onClick={handleLogout} className="w-full text-left font-mono text-[10px] tracking-wider uppercase font-bold text-red-400/60 hover:text-red-400 transition-colors px-2">
            ⚠️ Close Session Connection
          </button>
        </div>
      </div>

      {/* Main Screen Layout Canvas */}
      <div className="flex-1 flex flex-col bg-zinc-900/20 overflow-y-auto">
        {viewMode === 'chat' ? (
          <>
            {/* Wide Editorial Chat Stream Layout */}
            <div className="flex-1 overflow-y-auto p-8 space-y-6 max-w-3xl w-full mx-auto">
              {messages.length === 0 && (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-2 pt-36 select-none font-mono">
                  <h1 className="text-sm font-bold tracking-wider text-zinc-400 uppercase">Sovereign Cluster Pipeline Online</h1>
                  <p className="text-[11px] text-zinc-600 max-w-xs">Drop raw document extractions or sequence blocks into the transmission line.</p>
                </div>
              )}
              {messages.map((m, idx) => (
                <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`p-4 rounded-2xl max-w-xl text-xs leading-relaxed border ${m.role === 'user' ? 'bg-zinc-900 border-zinc-800 text-zinc-200' : 'bg-zinc-950 border-zinc-900 text-zinc-100 shadow-xl'}`}>
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

            {/* Input Submission Console Frame */}
            <div className="p-6 max-w-3xl w-full mx-auto">
              <form onSubmit={sendMessage} className="relative flex items-center shadow-2xl rounded-2xl border border-zinc-800 bg-zinc-950 p-2.5">
                <input type="text" value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} placeholder="Message your sequential cloud cluster pipelines..." className="flex-1 bg-transparent p-2 text-xs focus:outline-none text-zinc-100 placeholder-zinc-600" />
                <button type="submit" className="bg-white hover:bg-zinc-200 text-zinc-950 rounded-xl px-4 py-2.5 text-[11px] font-bold tracking-wide transition-all">Execute</button>
              </form>
            </div>
          </>
        ) : (
          /* HIGH-FIDELITY ADMINISTRATIVE RUNTIME DASHBOARD CONTROLS */
          <div className="p-8 max-w-4xl mx-auto w-full space-y-6">
            <div>
              <h1 className="text-xl font-bold tracking-tight text-white font-mono uppercase">🛠️ Core Infrastructure Settings</h1>
              <p className="text-xs text-zinc-500">Configure language mappings, secure secret validation codes, and distributed polyglot connections.</p>
            </div>

            {/* Sub-tab Ribbon Switcher Control Selection Menu */}
            <div className="flex space-x-1 border-b border-zinc-900 font-mono text-[11px] tracking-wider uppercase font-bold">
              <button onClick={() => setActiveSubTab('pipeline')} className={`px-4 py-2.5 border-b-2 transition-all ${activeSubTab === 'pipeline' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>⛓️ Pipeline Setup</button>
              <button onClick={() => setActiveSubTab('relays')} className={`px-4 py-2.5 border-b-2 transition-all ${activeSubTab === 'relays' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>🌐 Multi-SQL Relays</button>
              <button onClick={() => setActiveSubTab('vault')} className={`px-4 py-2.5 border-b-2 transition-all ${activeSubTab === 'vault' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>🔑 Key Vault</button>
              <button onClick={() => setActiveSubTab('security')} className={`px-4 py-2.5 border-b-2 transition-all ${activeSubTab === 'security' ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'}`}>🔒 Security Mgr</button>
            </div>

            {/* SUB-TAB CONTAINER 1: PIPELINE CONFIGURATION NODES */}
            {activeSubTab === 'pipeline' && (
              <div className="space-y-6">
                <div className="border border-zinc-800 rounded-xl overflow-hidden bg-zinc-950">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-zinc-900/70 border-b border-zinc-800 font-mono text-[10px] uppercase text-zinc-500 tracking-wider">
                      <tr><th className="p-3.5 text-center w-12">Pos</th><th className="p-3.5">Step Context Name</th><th className="p-3.5">Provider</th><th className="p-3.5">Model Variant Identity String</th></tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-900 font-mono text-[11px] text-zinc-300">
                      {pipelineSteps.map((s, i) => (
                        <tr key={i} className="hover:bg-zinc-900/30">
                          <td className="p-3.5 text-center text-indigo-400 font-bold">{s.sequence_order_position}</td>
                          <td className="p-3.5 text-white font-sans font-medium">{s.step_name}</td>
                          <td className="p-3.5"><span className="px-2 py-0.5 bg-zinc-900 border border-zinc-800 rounded text-zinc-400">{s.provider_type}</span></td>
                          <td className="p-3.5 text-zinc-400">{s.model_string}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <form onSubmit={handleAddStep} className="p-6 border border-zinc-800 rounded-xl space-y-4 bg-zinc-950/20">
                  <h3 className="text-xs font-bold text-zinc-300 font-mono uppercase tracking-wider">➕ Inject Pipeline Processing Step</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <input type="number" placeholder="Order Position" value={newStep.sequence_order_position} onChange={(e) => setNewStep({...newStep, sequence_order_position: parseInt(e.target.value)})} className="p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none" required />
                    <input type="text" placeholder="Step Name" value={newStep.step_name} onChange={(e) => setNewStep({...newStep, step_name: e.target.value})} className="p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none" required />
                    <select value={newStep.provider_type} onChange={(e) => setNewStep({...newStep, provider_type: e.target.value})} className="p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-zinc-400 focus:outline-none font-mono">
                      <option value="openrouter">OpenRouter Gateway</option>
                      <option value="google">Google AI Studio</option>
                    </select>
                    <input type="text" placeholder="Model Identifier Slug" value={newStep.model_string} onChange={(e) => setNewStep({...newStep, model_string: e.target.value})} className="p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none" required />
                  </div>
                  <textarea placeholder="System instructions / dynamic prompt guidance directives..." value={newStep.system_prompt_directives} onChange={(e) => setNewStep({...newStep, system_prompt_directives: e.target.value})} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white h-20 focus:outline-none" />
                  <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl px-4 py-2.5 text-xs font-bold font-mono tracking-wider uppercase">Save Node Parameters</button>
                </form>
              </div>
            )}

            {/* SUB-TAB CONTAINER 2: COMPLETE MULTI-SQL DATABASE RELAYS */}
            {activeSubTab === 'relays' && (
              <div className="space-y-6">
                <div className="p-4 bg-amber-950/20 border border-amber-900/40 rounded-xl text-amber-400 text-xs leading-relaxed font-mono">
                  ⚠️ <strong>Polyglot Decoupling:</strong> Swapping database connections routing changes database pointer matrices live across target nodes[cite: 3560]. Connection updates route transactional frames across decentralized instances dynamically with absolute zero gateway server down-time.
                </div>
                {/* Horizontal scroll container with micro padding isolates cell tables and prevents truncate deficits */}
                <div className="w-full border border-zinc-800 rounded-xl overflow-x-auto bg-zinc-950 shadow-2xl">
                  <div className="min-w-[650px]">
                    <table className="w-full text-left text-xs border-collapse table-fixed">
                      <thead className="bg-zinc-900/70 border-b border-zinc-800 font-mono text-[10px] uppercase text-zinc-500 tracking-wider">
                        <tr>
                          <th className="p-3.5 w-1/4 pl-5">Operational Duty</th>
                          <th className="p-3.5 w-3/4 pr-5">Active Target Database Cluster Target Connection URI Pointer String</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-900 font-mono text-[11px] text-zinc-300">
                        {dbRelays.map((r, i) => (
                          <tr key={i} className="hover:bg-zinc-900/30">
                            <td className="p-3.5 text-white font-bold uppercase tracking-wider pl-5">{r.operation_type}</td>
                            <td className="p-3.5 text-zinc-400 font-mono text-[10px] break-all select-all pr-5">{r.connection_string}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <form onSubmit={handleUpdateRelay} className="p-6 border border-zinc-800 rounded-xl space-y-4 bg-zinc-950/20">
                  <h3 className="text-xs font-bold text-zinc-300 font-mono uppercase tracking-wider">🌐 Hot-Swap Server Relational Destination Route</h3>
                  <div className="grid grid-cols-3 gap-4">
                    <select value={newRelay.operation_type} onChange={(e) => setNewRelay({...newRelay, operation_type: e.target.value})} className="col-span-1 p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-zinc-400 focus:outline-none font-mono">
                      <option value="master">Master Core Router</option>
                      <option value="metadata">Metadata Sidebar</option>
                      <option value="transactional">Transactional Logs</option>
                    </select>
                    <input type="text" placeholder="postgresql://username:password@ep-cluster-id.us-east-2.aws.neon.tech/neondb" value={newRelay.connection_string} onChange={(e) => setNewRelay({...newRelay, connection_string: e.target.value})} className="col-span-2 p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none" required />
                  </div>
                  <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl px-4 py-2.5 text-xs font-bold font-mono tracking-wider uppercase">Commit Network Switchover</button>
                </form>
              </div>
            )}

            {/* SUB-TAB CONTAINER 3: SECURE API KEY VAULT ROOM */}
            {activeSubTab === 'vault' && (
              <div className="space-y-6">
                <div className="border border-zinc-800 rounded-xl overflow-hidden bg-zinc-950 shadow-2xl">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-zinc-900/70 border-b border-zinc-800 font-mono text-[10px] uppercase text-zinc-500 tracking-wider">
                      <tr><th className="p-3.5 pl-5">Provider Token Slot</th><th className="p-3.5 pr-5">Masked Cryptographic Token Signature Mapping</th></tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-900 font-mono text-[11px] text-zinc-300">
                      {vaultKeys.map((k, i) => (
                        <tr key={i} className="hover:bg-zinc-900/30">
                          <td className="p-3.5 text-white font-bold uppercase pl-5">{k.provider_name}</td>
                          <td className="p-3.5 text-zinc-500 tracking-widest text-[10px] pr-5">{k.secret_key}</td>
                        </tr>
                      ))}
                      {vaultKeys.length === 0 && <tr><td colSpan="2" className="p-4 text-center text-zinc-600 italic font-sans">No verification tokens mapped in database vault storage yet.</td></tr>}
                    </tbody>
                  </table>
                </div>
                <form onSubmit={handleSaveVaultKey} className="p-6 border border-zinc-800 rounded-xl space-y-4 bg-zinc-950/20">
                  <h3 className="text-xs font-bold text-zinc-300 font-mono uppercase tracking-wider">🔑 Map Secure Authentication Token</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <select value={newKey.provider_name} onChange={(e) => setNewKey({...newKey, provider_name: e.target.value})} className="p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-zinc-400 focus:outline-none font-mono">
                      <option value="openrouter">OpenRouter Token Prefix</option>
                      <option value="google">Google AI Studio Token Prefix</option>
                    </select>
                    <input type="password" placeholder="sk-or-v1-••••••••" value={newKey.secret_key} onChange={(e) => setNewKey({...newKey, secret_key: e.target.value})} className="p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none" required />
                  </div>
                  <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl px-4 py-2.5 text-xs font-bold font-mono tracking-wider uppercase">Save Token Vault Mapping</button>
                </form>
              </div>
            )}

            {/* SUB-TAB CONTAINER 4: IDENTITY SECURITY MANAGER */}
            {activeSubTab === 'security' && (
              <form onSubmit={handleRotateSystemPassword} className="p-6 border border-zinc-800 rounded-xl space-y-4 bg-zinc-950/20 max-w-md">
                <h3 className="text-xs font-bold text-zinc-300 font-mono uppercase tracking-wider">🔒 Administrative Credentials Matrix</h3>
                <p className="text-[11px] text-zinc-500 leading-relaxed">Altering parameters here rotates encrypted security hashes stored on your Master Database node with zero script downtime.</p>
                <div className="space-y-3">
                  <input type="text" value="admin" className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-zinc-600 font-mono cursor-not-allowed select-none" disabled />
                  <input type="password" placeholder="New Production Passphrase String" value={rotatedPassword} onChange={(e) => setRotatedPassword(e.target.value)} className="w-full p-3 border border-zinc-800 rounded-xl bg-zinc-950 text-xs text-white focus:outline-none" required />
                </div>
                <button type="submit" className="bg-zinc-100 hover:bg-zinc-200 text-zinc-950 rounded-xl px-4 py-2.5 text-xs font-bold font-mono tracking-wider uppercase">Rotate Access Signatures</button>
              </form>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
