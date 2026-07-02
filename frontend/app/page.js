'use client';
import { useState, useEffect, useRef } from 'react';

export default function Home() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  
  const [viewMode, setViewMode] = useState('chat'); // chat or config
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [pipelineStatus, setPipelineStatus] = useState('');
  
  // Admin Configuration States
  const [pipelineSteps, setPipelineSteps] = useState([]);
  const [newStep, setNewStep] = useState({ sequence_order_position: 1, step_name: '', provider_type: 'openrouter', model_string: '', system_prompt_directives: '' });

  const messagesEndRef = useRef(null);
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:10000';

  useEffect(() => {
    const savedAuth = localStorage.getItem('fugu_auth_token');
    if (savedAuth) {
      setIsAuthenticated(true);
      fetchThreads();
      fetchPipelineConfig();
    }
  }, []);

  const handleLogin = (e) => {
    e.preventDefault();
    if (username === 'admin' && password === 'AdminSecure2026!') {
      localStorage.setItem('fugu_auth_token', 'secure_admin_signature');
      setIsAuthenticated(true);
      fetchThreads();
      fetchPipelineConfig();
    } else {
      setAuthError('Invalid credentials.');
    }
  };

  const fetchThreads = async () => {
    setThreads([{ id: 1, name: 'Sovereign Core Live Track' }]);
    setActiveThreadId(1);
  };

  const fetchPipelineConfig = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/config/pipeline`);
      if (res.ok) {
        const data = await res.json();
        setPipelineSteps(data);
      }
    } catch (e) { console.error("Failed to fetch layout configuration", e); }
  };

  const handleAddStep = async (e) => {
    e.preventDefault();
    const updatedSteps = [...pipelineSteps, newStep].sort((a, b) => a.sequence_order_position - b.sequence_order_position);
    try {
      const res = await fetch(`${backendUrl}/api/config/pipeline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedSteps)
      });
      if (res.ok) {
        setPipelineSteps(updatedSteps);
        setNewStep({ sequence_order_position: updatedSteps.length + 1, step_name: '', provider_type: 'openrouter', model_string: '', system_prompt_directives: '' });
      }
    } catch (e) { alert("Failed to commit routing adjustments."); }
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || !activeThreadId) return;

    const userPrompt = inputMessage;
    setInputMessage('');
    setMessages((prev) => [...prev, { role: 'user', content: userPrompt }]);

    try {
      const response = await fetch(`${backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: activeThreadId, content: userPrompt, username: 'admin', password_hash: 'AdminSecure2026!' })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantText = '';
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
              assistantText += parsed.token;
              setMessages((prev) => {
                const u = [...prev];
                u[u.length - 1].content = assistantText;
                return u;
              });
            }
          }
        }
      }
      setPipelineStatus('');
    } catch (error) { setPipelineStatus(`❌ Fault: ${error.message}`); }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-white">
        <form onSubmit={handleLogin} className="w-80 space-y-4 rounded-xl bg-zinc-900 p-6 border border-zinc-800 shadow-2xl">
          <h2 className="text-xl font-bold text-center">🔒 Sovereign Security Guard</h2>
          <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded bg-zinc-800 p-2 text-sm border border-zinc-700 text-white" />
          <input type="password" placeholder="Passphrase" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded bg-zinc-800 p-2 text-sm border border-zinc-700 text-white" />
          <button type="submit" className="w-full rounded bg-indigo-600 p-2 text-sm font-semibold">Verify Credentials</button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-50 text-zinc-900">
      {/* Sidebar Navigation */}
      <div className="w-64 bg-zinc-950 text-zinc-400 flex flex-col justify-between border-r border-zinc-800">
        <div className="p-4 space-y-4">
          <div className="flex justify-between items-center text-white font-bold px-2">
            <span>🎨 Fugu OS</span>
            <button onClick={() => setViewMode(viewMode === 'chat' ? 'config' : 'chat')} className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-2 py-1 rounded transition-colors">
              {viewMode === 'chat' ? '⚙️ Admin Console' : '💬 Return to Chat'}
            </button>
          </div>
        </div>
      </div>

      {/* Main Execution Viewport */}
      <div className="flex-1 flex flex-col justify-between bg-white overflow-y-auto">
        {viewMode === 'chat' ? (
          <>
            <div className="flex-1 p-8 space-y-6 max-w-3xl w-full mx-auto">
              {messages.map((m, idx) => (
                <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className="p-4 rounded-2xl border bg-zinc-50 max-w-xl text-sm">
                    <p className="font-mono text-xs text-zinc-400 mb-1 uppercase">{m.role}</p>
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                </div>
              ))}
              {pipelineStatus && <div className="text-xs font-mono text-indigo-600 animate-pulse">{pipelineStatus}</div>}
            </div>
            <div className="p-6 max-w-3xl w-full mx-auto">
              <form onSubmit={sendMessage} className="flex items-center border rounded-2xl p-2 bg-white">
                <input type="text" value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} placeholder="Send a multi-stage request..." className="flex-1 p-2 text-sm outline-none" />
                <button type="submit" className="bg-zinc-900 text-white rounded-xl px-4 py-2 text-xs">Execute</button>
              </form>
            </div>
          </>
        ) : (
          /* ACTIVE CONFIGURATION CONTROLS */
          <div className="p-8 max-w-4xl mx-auto w-full space-y-8">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">🛠️ Pipeline Sequence Core</h1>
              <p className="text-sm text-zinc-500">Add, edit, or modify your sequential language steps down below.</p>
            </div>

            {/* Current Pipeline Mappings Display */}
            <div className="border border-zinc-200 rounded-xl overflow-hidden">
              <table className="w-full text-left border-collapse text-sm">
                <thead className="bg-zinc-50 border-b border-zinc-200 font-mono text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="p-3">Pos</th>
                    <th className="p-3">Step Name</th>
                    <th className="p-3">Provider</th>
                    <th className="p-3">Model Variant Identifier</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {pipelineSteps.map((step, index) => (
                    <tr key={index} className="hover:bg-zinc-50/50">
                      <td className="p-3 font-mono font-bold text-indigo-600">{step.sequence_order_position}</td>
                      <td className="p-3 font-medium">{step.step_name}</td>
                      <td className="p-3"><span className="px-2 py-0.5 bg-zinc-100 rounded text-xs font-mono">{step.provider_type}</span></td>
                      <td className="p-3 font-mono text-xs text-zinc-600">{step.model_string}</td>
                    </tr>
                  ))}
                  {pipelineSteps.length === 0 && (
                    <tr>
                      <td colSpan="4" className="p-4 text-center text-zinc-400 text-xs">No model steps added to the SQL runtime database.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* New Structural Node Form Element */}
            <form onSubmit={handleAddStep} className="p-6 border border-zinc-200 rounded-xl space-y-4 bg-zinc-50/50">
              <h3 className="text-sm font-bold text-zinc-700">➕ Inject Dynamic Pipeline Step</h3>
              <div className="grid grid-cols-2 gap-4">
                <input type="number" placeholder="Position (e.g. 1)" value={newStep.sequence_order_position} onChange={(e) => setNewStep({...newStep, sequence_order_position: parseInt(e.target.value)})} className="p-2 border rounded bg-white text-sm" required />
                <input type="text" placeholder="Step Name (e.g. The Eye)" value={newStep.step_name} onChange={(e) => setNewStep({...newStep, step_name: e.target.value})} className="p-2 border rounded bg-white text-sm" required />
                <select value={newStep.provider_type} onChange={(e) => setNewStep({...newStep, provider_type: e.target.value})} className="p-2 border rounded bg-white text-sm">
                  <option value="openrouter">OpenRouter</option>
                  <option value="google">Google AI Studio</option>
                </select>
                <input type="text" placeholder="Model String (e.g. google/gemini-2.5-flash:free)" value={newStep.model_string} onChange={(e) => setNewStep({...newStep, model_string: e.target.value})} className="p-2 border rounded bg-white text-sm" required />
              </div>
              <textarea placeholder="System instructions / prompt guidelines..." value={newStep.system_prompt_directives} onChange={(e) => setNewStep({...newStep, system_prompt_directives: e.target.value})} className="w-full p-2 border rounded bg-white text-sm h-20" />
              <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-4 py-2 text-xs font-semibold transition-colors">Save Operational Directives</button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
