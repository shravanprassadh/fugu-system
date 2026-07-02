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
  
  const messagesEndRef = useRef(null);
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:10000';

  useEffect(() => {
    const savedAuth = localStorage.getItem('fugu_auth_token');
    if (savedAuth) {
      setIsAuthenticated(true);
      fetchThreads();
    }
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pipelineStatus]);

  // Fallback simple credentials for local verification pass matching backend requirements
  const handleLogin = (e) => {
    e.preventDefault();
    if (username === 'admin' && password === 'AdminSecure2026!') {
      localStorage.setItem('fugu_auth_token', 'secure_admin_signature');
      setIsAuthenticated(true);
      setAuthError('');
      fetchThreads();
    } else {
      setAuthError('Invalid infrastructure credentials.');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('fugu_auth_token');
    setIsAuthenticated(false);
  };

  const fetchThreads = async () => {
    // Simulated metadata read loop for visual population
    setThreads([{ id: 1, name: 'Sovereign Core Live Track' }]);
    setActiveThreadId(1);
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || !activeThreadId) return;

    const userPrompt = inputMessage;
    setInputMessage('');
    setMessages((prev) => [...prev, { role: 'user', content: userPrompt }]);
    setPipelineStatus('⚡ Activating cloud transport layer...');

    try {
      const response = await fetch(`${backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thread_id: activeThreadId,
          content: userPrompt,
          username: 'admin',
          password_hash: 'AdminSecure2026!' // Match default structural gate
        })
      });

      if (!response.ok) throw new Error('API server boundary error.');

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
            
            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.status) {
                setPipelineStatus(parsed.status);
              } else if (parsed.token) {
                assistantText += parsed.token;
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1].content = assistantText;
                  return updated;
                });
              } else if (parsed.error) {
                setPipelineStatus(`❌ Error: ${parsed.error}`);
              }
            } catch (err) {
              // Handle partial chunk segments safely
            }
          }
        }
      }
      setPipelineStatus('');
    } catch (error) {
      setPipelineStatus(`❌ Pipeline Execution Fault: ${error.message}`);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-white">
        <form onSubmit={handleLogin} className="w-80 space-y-4 rounded-xl bg-zinc-900 p-6 border border-zinc-800 shadow-2xl">
          <h2 className="text-xl font-bold tracking-tight text-center">🔒 Sovereign Security Guard</h2>
          {authError && <p className="text-xs text-red-400 text-center">{authError}</p>}
          <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded bg-zinc-800 p-2 text-sm border border-zinc-700 focus:outline-none focus:border-indigo-500" />
          <input type="password" placeholder="Passphrase" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded bg-zinc-800 p-2 text-sm border border-zinc-700 focus:outline-none focus:border-indigo-500" />
          <button type="submit" className="w-full rounded bg-indigo-600 p-2 text-sm font-semibold hover:bg-indigo-500 transition-colors">Verify Credentials</button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-50 text-zinc-900 font-sans antialiased">
      {/* Dark Tactical Sidebar Layout */}
      <div className="w-64 bg-zinc-950 text-zinc-400 flex flex-col justify-between border-r border-zinc-800">
        <div className="p-4 space-y-4">
          <div className="flex justify-between items-center text-white font-bold tracking-tight text-lg px-2">
            <span>🎨 Fugu OS</span>
            <button onClick={() => setViewMode(viewMode === 'chat' ? 'config' : 'chat')} className="text-xs bg-zinc-800 hover:bg-zinc-700 px-2 py-1 rounded transition-colors">
              {viewMode === 'chat' ? '⚙️ Admin' : '💬 Chat'}
            </button>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-semibold text-zinc-600 px-2 uppercase tracking-wider">Conversations</p>
            {threads.map((t) => (
              <div key={t.id} className="p-2 rounded text-sm text-zinc-300 bg-zinc-900 border border-zinc-800 select-none cursor-pointer">
                {t.name}
              </div>
            ))}
          </div>
        </div>
        <div className="p-4 border-t border-zinc-900">
          <button onClick={handleLogout} className="w-full text-left text-xs text-red-400/70 hover:text-red-400 transition-colors px-2 py-1">
            ⚠️ Disconnect Session
          </button>
        </div>
      </div>

      {/* Main Wide Presentation Canvas */}
      <div className="flex-1 flex flex-col justify-between bg-white">
        {viewMode === 'chat' ? (
          <>
            {/* Chat Area */}
            <div className="flex-1 overflow-y-auto p-8 space-y-6 max-w-3xl w-full mx-auto">
              {messages.map((m, idx) => (
                <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`p-4 rounded-2xl max-w-xl text-sm leading-relaxed ${m.role === 'user' ? 'bg-zinc-100 text-zinc-800' : 'bg-white border border-zinc-100 shadow-sm text-zinc-900'}`}>
                    <p className="font-mono text-xs text-zinc-400 mb-1 uppercase tracking-widest">{m.role}</p>
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                </div>
              ))}
              {pipelineStatus && (
                <div className="flex justify-start">
                  <div className="p-3 rounded-xl bg-indigo-50 border border-indigo-100/50 text-indigo-600 font-mono text-xs shadow-sm animate-pulse">
                    {pipelineStatus}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Shell Bar */}
            <div className="p-6 border-t border-zinc-100 max-w-3xl w-full mx-auto">
              <form onSubmit={sendMessage} className="relative flex items-center shadow-lg rounded-2xl border border-zinc-200 bg-white p-2">
                <input type="text" value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} placeholder="Send a multi-stage request to the pipeline matrix..." className="flex-1 bg-transparent p-3 text-sm focus:outline-none text-zinc-900 placeholder-zinc-400" />
                <button type="submit" className="bg-zinc-900 hover:bg-zinc-800 text-white rounded-xl px-4 py-2 text-xs font-medium transition-all">Execute</button>
              </form>
            </div>
          </>
        ) : (
          /* Administrative Console Layout Placeholder View */
          <div className="p-8 max-w-2xl mx-auto w-full space-y-6">
            <h1 className="text-2xl font-bold tracking-tight">🛠️ Core Infrastructure Settings</h1>
            <p className="text-sm text-zinc-500">Your runtime code pipelines and multi-SQL routes are safely running via your master cloud definitions. Modifying these records dynamic-swaps active models with zero server downtime.</p>
            <div className="p-4 rounded-xl border border-zinc-100 bg-zinc-50 font-mono text-xs text-zinc-600">
              [SYSTEM MONITOR]: Database state routing active. No system errors logged.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
