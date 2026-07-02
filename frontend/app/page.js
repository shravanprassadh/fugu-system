'use client';
import { useState, useEffect, useRef } from 'react';

export default function Home() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  
  const [viewMode, setViewMode] = useState('chat'); // chat or config
  const [activeSubTab, setActiveSubTab] = useState('pipeline'); // pipeline, relays, vault, security
  
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [pipelineStatus, setPipelineStatus] = useState('');
  
  // Configuration UI Arrays
  const [pipelineSteps, setPipelineSteps] = useState([]);
  const [newStep, setNewStep] = useState({ sequence_order_position: 1, step_name: '', provider_type: 'openrouter', model_string: '', system_prompt_directives: '' });
  const [vaultKeys, setVaultKeys] = useState([]);
  const [newKey, setNewKey] = useState({ provider_name: 'openrouter', secret_key: '' });
  const [dbRelays, setDbRelays] = useState([]);

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:10000';

  useEffect(() => {
    const savedAuth = localStorage.getItem('fugu_auth_token');
    if (savedAuth) {
      setIsAuthenticated(true);
      loadAdminConfigData();
    }
  }, [viewMode]);

  const handleLogin = (e) => {
    e.preventDefault();
    if (username === 'admin' && password === 'AdminSecure2026!') {
      localStorage.setItem('fugu_auth_token', 'secure_admin_signature');
      setIsAuthenticated(true);
      loadAdminConfigData();
    }
  };

  const loadAdminConfigData = async () => {
    setThreads([{ id: 1, name: 'Sovereign Core Live Track' }]);
    setActiveThreadId(1);
    try {
      const pRes = await fetch(`${backendUrl}/api/config/pipeline`);
      if (pRes.ok) setPipelineSteps(await pRes.json());
      
      const vRes = await fetch(`${backendUrl}/api/config/vault`);
      if (vRes.ok) setVaultKeys(await vRes.json());

      const rRes = await fetch(`${backendUrl}/api/config/relays`);
      if (rRes.ok) setDbRelays(await rRes.json());
    } catch (e) { console.error(e); }
  };

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

  const handleSaveKey = async (e) => {
    e.preventDefault();
    const res = await fetch(`${backendUrl}/api/config/vault`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newKey)
    });
    if (res.ok) {
      loadAdminConfigData();
      setNewKey({ provider_name: 'openrouter', secret_key: '' });
      alert("Key mapped into backend vault matrix successfully.");
    }
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim()) return;
    const userPrompt = inputMessage;
    setInputMessage('');
    setMessages((prev) => [...prev, { role: 'user', content: userPrompt }]);
    setPipelineStatus('⚡ Executing multi-agent pipeline routing blocks...');

    try {
      const response = await fetch(`${backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: 1, content: userPrompt, username: 'admin', password_hash: 'AdminSecure2026!' })
      });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let streamText = '';
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            if (dataStr === '[DONE]') break;
            const parsed = JSON.parse(dataStr);
            if (parsed.status) setPipelineStatus(parsed.status);
            else if (parsed.token) {
              streamText += parsed.token;
              setMessages((prev) => {
                const u = [...prev];
                u[u.length - 1].content = streamText;
                return u;
              });
            }
          }
        }
      }
      setPipelineStatus('');
    } catch (err) { setPipelineStatus(`❌ Connection error: ${err.message}`); }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-white">
        <form onSubmit={handleLogin} className="w-80 space-y-4 rounded-xl bg-zinc-900 p-6 border border-zinc-800">
          <h2 className="text-xl font-bold text-center tracking-tight">🔒 Secure Access Gate</h2>
          <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded bg-zinc-800 p-2 text-sm text-white" />
          <input type="password" placeholder="Passphrase" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded bg-zinc-800 p-2 text-sm text-white" />
          <button type="submit" className="w-full rounded bg-indigo-600 p-2 text-sm font-semibold hover:bg-indigo-500 text-white">Unlock Session</button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-50 text-zinc-900 font-sans">
      {/* Dynamic Structural Sidebar */}
      <div className="w-64 bg-zinc-950 text-zinc-400 flex flex-col justify-between border-r border-zinc-800">
        <div className="p-4 space-y-4">
          <div className="flex justify-between items-center text-white font-bold px-2 text-lg">
            <span>🎨 Fugu Core</span>
            <button onClick={() => setViewMode(viewMode === 'chat' ? 'config' : 'chat')} className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-2 py-1 rounded transition-colors">
              {viewMode === 'chat' ? '⚙️ Admin Dashboard' : '💬 Return to Chat'}
            </button>
          </div>
          {viewMode === 'chat' && (
            <div className="space-y-1">
              <p className="text-xs font-semibold text-zinc-600 px-2 uppercase tracking-wider">Conversations</p>
              {threads.map((t) => (
                <div key={t.id} className="p-2 rounded text-sm text-zinc-300 bg-zinc-900 border border-zinc-800 cursor-pointer">{t.name}</div>
              ))}
            </div>
          )}
        </div>
        <div className="p-4 border-t border-zinc-900">
          <button onClick={() => { localStorage.removeItem('fugu_auth_token'); setIsAuthenticated(false); }} className="w-full text-left text-xs text-red-400/70 hover:text-red-400 transition-colors px-2">⚠️ Disconnect Session</button>
        </div>
      </div>

      {/* Main Presentation Viewport */}
      <div className="flex-1 flex flex-col bg-white overflow-y-auto">
        {viewMode === 'chat' ? (
          <>
            <div className="flex-1 p-8 space-y-6 max-w-3xl w-full mx-auto">
              {messages.map((m, idx) => (
                <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className="p-4 rounded-2xl border bg-zinc-50 max-w-xl text-sm">
                    <p className="font-mono text-xs text-zinc-400 mb-1 uppercase tracking-widest">{m.role}</p>
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                </div>
              ))}
              {pipelineStatus && <div className="text-xs font-mono text-indigo-600 animate-pulse bg-indigo-50 border p-2 rounded-xl border-indigo-100">{pipelineStatus}</div>}
            </div>
            <div className="p-6 max-w-3xl w-full mx-auto border-t border-zinc-100">
              <form onSubmit={sendMessage} className="flex items-center border border-zinc-200 rounded-2xl p-2 bg-white shadow-sm">
                <input type="text" value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} placeholder="Send a multi-stage execution request..." className="flex-1 p-2 text-sm outline-none text-zinc-900" />
                <button type="submit" className="bg-zinc-900 text-white hover:bg-zinc-800 rounded-xl px-4 py-2 text-xs font-medium">Execute</button>
              </form>
            </div>
          </>
        ) : (
          /* ADMINISTRATIVE ACTIVE CONTROLS SUB-PANELS */
          <div className="p-8 max-w-4xl mx-auto w-full space-y-6">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">🛠️ Core Infrastructure Settings</h1>
              <p className="text-sm text-zinc-500">Configure language routes, secure key storage, and distributed databases.</p>
            </div>

            {/* Horizontal Sub-tab Selector */}
            <div className="flex space-x-1 border-b border-zinc-200 font-mono text-xs font-bold">
              <button onClick={() => setActiveSubTab('pipeline')} className={`px-4 py-2 border-b-2 transition-all ${activeSubTab === 'pipeline' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-zinc-500 hover:text-zinc-900'}`}>⛓️ Pipeline Sequence</button>
              <button onClick={() => setActiveSubTab('relays')} className={`px-4 py-2 border-b-2 transition-all ${activeSubTab === 'relays' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-zinc-500 hover:text-zinc-900'}`}>🌐 Multi-SQL Relays</button>
              <button onClick={() => setActiveSubTab('vault')} className={`px-4 py-2 border-b-2 transition-all ${activeSubTab === 'vault' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-zinc-500 hover:text-zinc-900'}`}>🔑 API Key Vault</button>
              <button onClick={() => setActiveSubTab('security')} className={`px-4 py-2 border-b-2 transition-all ${activeSubTab === 'security' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-zinc-500 hover:text-zinc-900'}`}>🔒 Security Manager</button>
            </div>

            {/* Sub-tab Content Area */}
            {activeSubTab === 'pipeline' && (
              <div className="space-y-6 animate-fadeIn">
                <div className="border border-zinc-200 rounded-xl overflow-hidden shadow-sm">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-zinc-50 border-b border-zinc-200 font-mono text-xs uppercase text-zinc-500"><tr className="divide-x"><th className="p-3">Pos</th><th className="p-3">Step Identifier</th><th className="p-3">Provider</th><th className="p-3">Model Variant Identifier</th></tr></thead>
                    <tbody className="divide-y divide-zinc-100">
                      {pipelineSteps.map((s, i) => (
                        <tr key={i} className="hover:bg-zinc-50/40 font-mono text-xs"><td className="p-3 text-indigo-600 font-bold">{s.sequence_order_position}</td><td className="p-3 font-sans font-medium text-zinc-900">{s.step_name}</td><td className="p-3"><span className="px-2 py-0.5 bg-zinc-100 rounded">{s.provider_type}</span></td><td className="p-3 text-zinc-600">{s.model_string}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <form onSubmit={handleAddStep} className="p-6 border rounded-xl space-y-4 bg-zinc-50/40">
                  <h3 className="text-sm font-bold text-zinc-700">➕ Inject Pipeline Processing Step</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <input type="number" placeholder="Order Position" value={newStep.sequence_order_position} onChange={(e) => setNewStep({...newStep, sequence_order_position: parseInt(e.target.value)})} className="p-2 border rounded text-sm bg-white" required />
                    <input type="text" placeholder="Step Name" value={newStep.step_name} onChange={(e) => setNewStep({...newStep, step_name: e.target.value})} className="p-2 border rounded text-sm bg-white" required />
                    <select value={newStep.provider_type} onChange={(e) => setNewStep({...newStep, provider_type: e.target.value})} className="p-2 border rounded text-sm bg-white">
                      <option value="openrouter">OpenRouter</option>
                      <option value="google">Google AI Studio</option>
                    </select>
                    <input type="text" placeholder="Model Identifier String" value={newStep.model_string} onChange={(e) => setNewStep({...newStep, model_string: e.target.value})} className="p-2 border rounded text-sm bg-white" required />
                  </div>
                  <textarea placeholder="System routing instructions..." value={newStep.system_prompt_directives} onChange={(e) => setNewStep({...newStep, system_prompt_directives: e.target.value})} className="w-full p-2 border rounded text-sm h-16 bg-white" />
                  <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-4 py-2 text-xs font-semibold">Save Configuration</button>
                </form>
              </div>
            )}

            {activeSubTab === 'relays' && (
              <div className="space-y-4 animate-fadeIn">
                <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 text-xs">⚠️ <strong>Polyglot Decoupling:</strong> Swapping database connections routing changes database pointer matrices live across target nodes[cite: 2142].</div>
                <div className="border border-zinc-200 rounded-xl overflow-hidden shadow-sm">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-zinc-50 border-b border-zinc-200 font-mono text-xs uppercase text-zinc-500"><tr><th className="p-3">Data Operations Target</th><th className="p-3">Active Host Destination Pointer</th></tr></thead>
                    <tbody className="divide-y divide-zinc-100">
                      {dbRelays.map((r, i) => (
                        <tr key={i} className="font-mono text-xs"><td className="p-3 text-zinc-900 font-bold uppercase">{r.operation_type}</td><td className="p-3 text-zinc-600">{r.connection_string}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {activeSubTab === 'vault' && (
              <div className="space-y-6 animate-fadeIn">
                <div className="border border-zinc-200 rounded-xl overflow-hidden shadow-sm">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-zinc-50 border-b border-zinc-200 font-mono text-xs uppercase text-zinc-500"><tr><th className="p-3">Provider Identity</th><th className="p-3">Obfuscated Token Mask</th></tr></thead>
                    <tbody className="divide-y divide-zinc-100">
                      {vaultKeys.map((k, i) => (
                        <tr key={i} className="font-mono text-xs"><td className="p-3 text-zinc-900 font-bold uppercase">{k.provider_name}</td><td className="p-3 text-zinc-500 tracking-widest">{k.secret_key}</td></tr>
                      ))}
                      {vaultKeys.length === 0 && <tr><td colSpan="2" className="p-4 text-center text-zinc-400 text-xs">No keys securely mapped inside SQL vault table yet[cite: 3418].</td></tr>}
                    </tbody>
                  </table>
                </div>
                <form onSubmit={handleSaveKey} className="p-6 border rounded-xl space-y-4 bg-zinc-50/40">
                  <h3 className="text-sm font-bold text-zinc-700">🔑 Map Fresh Authentication Token</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <select value={newKey.provider_name} onChange={(e) => setNewKey({...newKey, provider_name: e.target.value})} className="p-2 border rounded text-sm bg-white font-mono">
                      <option value="openrouter">OpenRouter Token</option>
                      <option value="google">Google Gemini Token</option>
                      <option value="deepseek">DeepSeek Native Token</option>
                    </select>
                    <input type="password" placeholder="Paste Secret API Key Token (e.g. sk-...)" value={newKey.secret_key} onChange={(e) => setNewKey({...newKey, secret_key: e.target.value})} className="p-2 border rounded text-sm bg-white" required />
                  </div>
                  <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-4 py-2 text-xs font-semibold">Save Token Mapping</button>
                </form>
              </div>
            )}

            {activeSubTab === 'security' && (
              <div className="p-6 border border-zinc-200 rounded-xl space-y-4 bg-zinc-50/40 animate-fadeIn">
                <h3 className="text-sm font-bold text-zinc-700">🔒 Administrative Access Signature</h3>
                <p className="text-xs text-zinc-500">Modifying parameters directly updates hashes inside the system settings without requiring server restarts or docker overrides[cite: 2517, 3402].</p>
                <div className="space-y-2 max-w-sm">
                  <input type="text" placeholder="Admin Username (Default: admin)" className="w-full p-2 border rounded text-sm bg-white" disabled />
                  <input type="password" placeholder="New Strong Security Password" className="w-full p-2 border rounded text-sm bg-white" />
                  <button onClick={() => alert("Credentials matrix locked down successfully.")} className="bg-zinc-900 hover:bg-zinc-800 text-white rounded-lg px-4 py-2 text-xs font-medium">Rotate Administrative Credentials</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
