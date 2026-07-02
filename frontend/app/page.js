"use client"

import React, { useState, useEffect, useRef } from 'react'
import { MessageSquare, Plus, Send, Settings, Shield, RefreshCw, Sparkles, User, Terminal, Database, Sliders, ArrowLeft, Lock, Key, Trash2, LogOut, Varticon } from 'lucide-react'

export default function Workspace() {
  // Authentication & Security Elements
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [usernameInput, setUsernameInput] = useState('')
  const [passwordInput, setPasswordInput] = useState('')
  const [authError, setAuthError] = useState('')
  
  // Interface View Navigation Map
  const [viewMode, setViewMode] = useState('chat') 
  const [adminTab, setAdminTab] = useState('pipeline') 
  
  // Data State Channels
  const [threads, setThreads] = useState([])
  const [activeThreadId, setActiveThreadId] = useState(null)
  const [activeThreadName, setActiveThreadName] = useState('')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [newThreadName, setNewThreadName] = useState('')
  
  // Cluster Configurations Fields State
  const [stepNum, setStepNum] = useState(1)
  const [stepName, setStepName] = useState('Sovereign Auto-Core')
  const [providerId, setProviderId] = useState('openrouter')
  const [modelId, setModelId] = useState('openrouter/free')
  const [sysPrompt, setSysPrompt] = useState('You are a helpful assistant.')
  const [codeBody, setCodeBody] = useState(`def execute_step(payload, system_prompt, model_string, api_key):\n    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)\n    response = client.chat.completions.create(\n        model=model_string,\n        messages=[\n            {"role": "system", "content": system_prompt},\n            {"role": "user", "content": payload}\n        ]\n    )\n    return response.choices[0].message.content`)
  
  const [threadsUrl, setThreadsUrl] = useState('')
  const [messagesUrl, setMessagesUrl] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  
  // API Keys Dynamic Vault Form States
  const [vaultKeys, setVaultKeys] = useState([])
  const [vaultProviderInput, setVaultProviderInput] = useState('')
  const [vaultKeyInput, setVaultKeyInput] = useState('')
  
  const [adminMessage, setAdminMessage] = useState({ type: '', text: '' })
  const messagesEndRef = useRef(null)
  const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || ''

  useEffect(() => {
    const activeSession = localStorage.getItem('fugu_session_secure')
    if (activeSession === 'true') setIsAuthenticated(true)
  }, [])

  useEffect(() => {
    if (isAuthenticated) fetchThreads()
  }, [isAuthenticated])

  useEffect(() => {
    if (activeThreadId && viewMode === 'chat' && isAuthenticated) {
      fetchMessages(activeThreadId)
    }
  }, [activeThreadId, viewMode, isAuthenticated])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleAuthentication = async (e) => {
    e.preventDefault()
    setAuthError('')
    try {
      const encoder = new TextEncoder()
      const data = encoder.encode(passwordInput)
      const hashBuffer = await crypto.subtle.digest('SHA-256', data)
      const hashArray = Array.from(new Uint8Array(hashBuffer))
      const clientHash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('')

      const res = await fetch(`${BACKEND_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: usernameInput, password_hash: clientHash })
      })

      if (res.ok) {
        localStorage.setItem('fugu_session_secure', 'true')
        setIsAuthenticated(true)
      } else {
        setAuthError('Access Denied. Signature mismatch.')
      }
    } catch (err) {
      setAuthError('Security infrastructure handoff failed.')
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('fugu_session_secure')
    setIsAuthenticated(false)
    setViewMode('chat')
    setUsernameInput('')
    setPasswordInput('')
  }

  const fetchThreads = async (selectTargetId = null) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/threads`)
      const data = await res.json()
      if (data.threads) {
        setThreads(data.threads)
        if (data.threads.length > 0) {
          if (selectTargetId) {
            const match = data.threads.find(t => t.id === selectTargetId)
            if (match) {
              setActiveThreadId(match.id)
              setActiveThreadName(match.name)
              return
            }
          }
          if (!activeThreadId || !data.threads.some(t => t.id === activeThreadId)) {
            setActiveThreadId(data.threads[0].id)
            setActiveThreadName(data.threads[0].name)
          }
        } else {
          setActiveThreadId(null)
          setActiveThreadName('')
          setMessages([])
        }
      }
    } catch (err) {
      console.error(err)
    }
  }

  const fetchMessages = async (threadId) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/threads/${threadId}/messages`)
      const data = await res.json()
      if (data.messages) setMessages(data.messages)
    } catch (err) {
      console.error(err)
    }
  }

  const fetchAdminConfig = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/config`)
      const data = await res.json()
      if (data.pipeline && data.pipeline.length > 0) {
        const primary = data.pipeline[0]
        setStepNum(primary.step_num)
        setStepName(primary.step_name)
        setProviderId(primary.provider_identifier)
        setModelId(primary.model_string)
        setSysPrompt(primary.system_prompt)
        setCodeBody(primary.python_code_body)
      }
      if (data.relays) {
        const tRelay = data.relays.find(r => r.operation === 'threads')
        const mRelay = data.relays.find(r => r.operation === 'messages')
        setThreadsUrl(tRelay ? tRelay.connection_string : '')
        setMessagesUrl(mRelay ? mRelay.connection_string : '')
      }
      fetchVaultKeys()
    } catch (err) {
      console.error(err)
    }
  }

  const fetchVaultKeys = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/keys`)
      const data = await res.json()
      if (data.keys) setVaultKeys(data.keys)
    } catch (err) {
      console.error(err)
    }
  }

  const createThread = async (e) => {
    e.preventDefault()
    if (!newThreadName.trim()) return
    try {
      await fetch(`${BACKEND_URL}/api/threads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newThreadName })
      })
      const targetName = newThreadName
      setNewThreadName('')
      
      const res = await fetch(`${BACKEND_URL}/api/threads`)
      const data = await res.json()
      if (data.threads) {
        setThreads(data.threads)
        const newlyCreated = data.threads.find(t => t.name === targetName)
        if (newlyCreated) {
          setActiveThreadId(newlyCreated.id)
          setActiveThreadName(newlyCreated.name)
        }
      }
    } catch (err) {
      console.error(err)
    }
  }

  const deleteThread = async (e, threadId) => {
    e.stopPropagation() 
    if (!confirm("Are you sure you want to permanently purge this chat register?")) return
    try {
      const res = await fetch(`${BACKEND_URL}/api/threads/${threadId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error("Cluster rejected data deletion request.")
      if (activeThreadId === threadId) {
        const remaining = threads.filter(t => t.id !== threadId)
        if (remaining.length > 0) {
          setActiveThreadId(remaining[0].id)
          setActiveThreadName(remaining[0].name)
        } else {
          setActiveThreadId(null)
          setActiveThreadName('')
          setMessages([])
        }
      }
      await fetchThreads()
    } catch (err) {
      alert(err.message)
    }
  }

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!input.trim() || !activeThreadId || loading) return

    const userMessage = input
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])
    setLoading(true)

    try {
      const res = await fetch(`${BACKEND_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: activeThreadId, prompt: userMessage })
      })
      if (!res.ok) {
        const errData = await res.json()
        throw new Error(errData.detail || "Pipeline network breakdown.")
      }
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.content }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `🚨 Core Fault: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }

  const savePipeline = async (e) => {
    e.preventDefault()
    setAdminMessage({ type: '', text: '' })
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/pipeline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          step_num: stepNum,
          step_name: stepName,
          provider_identifier: providerId,
          model_string: modelId,
          system_prompt: sysPrompt,
          python_code_body: codeBody
        })
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || "Invalid schema.")
      }
      setAdminMessage({ type: 'success', text: 'Pipeline layers committed.' })
    } catch (err) {
      setAdminMessage({ type: 'error', text: err.message })
    }
  }

  const saveRelays = async (e) => {
    e.preventDefault()
    setAdminMessage({ type: '', text: '' })
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/relays`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threads_url: threadsUrl, messages_url: messagesUrl })
      })
      if (!res.ok) throw new Error("Database network configuration dropped.")
      setAdminMessage({ type: 'success', text: 'Database relays pointing cleanly.' })
    } catch (err) {
      setAdminMessage({ type: 'error', text: err.message })
    }
  }

  const changeCredentials = async (e) => {
    e.preventDefault()
    setAdminMessage({ type: '', text: '' })
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/credentials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_username: newUsername, new_password_raw: newPassword })
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || "Validation constraint failed.")
      }
      setAdminMessage({ type: 'success', text: 'Master credential matrix overwritten inside SQL records.' })
      setNewUsername('')
      setNewPassword('')
    } catch (err) {
      setAdminMessage({ type: 'error', text: err.message })
    }
  }

  const saveVaultKey = async (e) => {
    e.preventDefault()
    setAdminMessage({ type: '', text: '' })
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_identifier: vaultProviderInput, api_key: vaultKeyInput })
      })
      if (!res.ok) throw new Error("Vault routing drop error occurred.")
      setAdminMessage({ type: 'success', text: `API key saved cleanly for platform identifier: "${vaultProviderInput.toLowerCase()}".` })
      setVaultProviderInput('')
      setVaultKeyInput('')
      fetchVaultKeys()
    } catch (err) {
      setAdminMessage({ type: 'error', text: err.message })
    }
  }

  const deleteVaultKey = async (providerId) => {
    if (!confirm(`Confirm complete wipe of authorization credentials for provider: "${providerId}"?`)) return
    setAdminMessage({ type: '', text: '' })
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/keys/${providerId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error("Purge transaction rejected by cluster.")
      setAdminMessage({ type: 'success', text: `Provider credentials wiped for: "${providerId}".` })
      fetchVaultKeys()
    } catch (err) {
      setAdminMessage({ type: 'error', text: err.message })
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="w-screen h-screen bg-zinc-950 flex flex-col items-center justify-center font-sans antialiased px-4">
        <div className="max-w-sm w-full bg-zinc-900 border border-zinc-800/80 rounded-2xl p-8 shadow-[0_20px_50px_rgba(0,0,0,0.5)] flex flex-col">
          <div className="w-12 h-12 rounded-xl bg-blue-600/10 border border-blue-500/20 flex items-center justify-center mb-5 text-blue-400 self-center">
            <Lock className="w-5 h-5" />
          </div>
          <div className="text-center mb-6">
            <h2 className="text-zinc-100 font-medium text-base tracking-tight">Sovereign Cluster Node</h2>
            <p className="text-zinc-500 text-xs mt-1 leading-relaxed">Enter secure session coordinates to interface with the core layer.</p>
          </div>
          <form onSubmit={handleAuthentication} className="w-full flex flex-col gap-3.5">
            <input
              type="text"
              placeholder="Username..."
              value={usernameInput}
              onChange={(e) => setUsernameInput(e.target.value)}
              className="w-full text-xs bg-zinc-950 text-zinc-200 border border-zinc-800 rounded-xl px-4 py-3.5 focus:outline-none focus:border-zinc-700 transition-all font-mono"
            />
            <input
              type="password"
              placeholder="Password..."
              value={passwordInput}
              onChange={(e) => setPasswordInput(e.target.value)}
              className="w-full text-xs bg-zinc-950 text-zinc-200 border border-zinc-800 rounded-xl px-4 py-3.5 focus:outline-none focus:border-zinc-700 transition-all font-mono"
            />
            {authError && <p className="text-red-400 text-[11px] font-medium leading-normal px-1">{authError}</p>}
            <button type="submit" className="w-full bg-zinc-100 hover:bg-zinc-200 text-zinc-950 font-semibold text-xs py-3.5 rounded-xl transition-all mt-1">
              Authenticate Node Access
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen w-screen bg-white overflow-hidden font-sans antialiased text-zinc-900">
      
      {/* SIDEBAR */}
      <div className="w-72 bg-zinc-950 flex flex-col flex-shrink-0 h-full border-r border-zinc-800/40">
        <div className="p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2.5">
              <div className="w-5 h-5 rounded-md bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
                <Sparkles className="w-3 h-3 text-white" />
              </div>
              <span className="text-sm font-medium tracking-tight text-zinc-200">Sovereign OS</span>
            </div>
            <span className="text-[10px] font-mono tracking-widest text-zinc-500 uppercase bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">v1.2</span>
          </div>
          
          <form onSubmit={createThread} className="relative flex items-center">
            <input
              type="text"
              placeholder="New workspace track..."
              value={newThreadName}
              onChange={(e) => setNewThreadName(e.target.value)}
              className="w-full text-xs bg-zinc-900/60 text-zinc-200 placeholder-zinc-500 border border-zinc-800/80 rounded-xl pl-3.5 pr-10 py-3 focus:outline-none focus:border-zinc-700 focus:bg-zinc-900 transition-all duration-200"
              disabled={viewMode === 'admin'}
            />
            <button type="submit" disabled={viewMode === 'admin'} className="absolute right-2 p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/80 transition-all disabled:opacity-30">
              <Plus className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>

        <div className="flex-1 overflow-y-auto px-3 flex flex-col gap-1 select-none scrollbar-none">
          <p className="text-[10px] font-semibold text-zinc-500 px-3 tracking-widest uppercase mb-2 mt-2">Active Registers</p>
          {threads.map((t) => {
            const isActive = activeThreadId === t.id && viewMode === 'chat'
            return (
              <button
                key={t.id}
                onClick={() => {
                  setViewMode('chat')
                  setActiveThreadId(t.id)
                  setActiveThreadName(t.name)
                }}
                className={`w-full flex items-center justify-between px-3.5 py-3 rounded-xl text-xs font-medium text-left transition-all duration-200 group relative ${
                  isActive ? 'bg-zinc-900 text-zinc-100 border border-zinc-800/60 shadow-inner' : 'text-zinc-400 hover:bg-zinc-900/40 hover:text-zinc-200'
                }`}
              >
                <div className="flex items-center gap-3 truncate mr-6">
                  <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 transition-colors ${isActive ? 'text-blue-400' : 'text-zinc-500 group-hover:text-zinc-400'}`} />
                  <span className="truncate tracking-wide">{t.name}</span>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span onClick={(e) => deleteThread(e, t.id)} className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-zinc-800/80 text-zinc-500 hover:text-red-400 transition-all duration-150 relative z-20">
                    <Trash2 className="w-3.5 h-3.5" />
                  </span>
                  {isActive && <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shadow-sm shadow-blue-400" />}
                </div>
              </button>
            )
          })}
        </div>

        <div className="p-4 border-t border-zinc-900 bg-zinc-950/80 flex flex-col gap-2">
          <button 
            onClick={() => {
              setViewMode('admin')
              setAdminMessage({ type: '', text: '' })
              fetchAdminConfig()
            }}
            className={`w-full flex items-center gap-3 px-3.5 py-3 rounded-xl text-xs font-medium transition-all duration-200 border ${
              viewMode === 'admin' ? 'bg-blue-600 text-white border-blue-500 shadow-md shadow-blue-600/10' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200 border-transparent hover:border-zinc-800/40'
            }`}
          >
            <Settings className={`w-4 h-4 ${viewMode === 'admin' ? 'text-white' : 'text-zinc-500'}`} />
            <span className="tracking-wide">Cluster Configuration</span>
          </button>
          <button onClick={handleLogout} className="w-full flex items-center gap-3 px-3.5 py-3 rounded-xl text-xs font-medium text-zinc-500 hover:text-red-400 hover:bg-red-950/20 border border-transparent hover:border-red-900/30 transition-all duration-200">
            <LogOut className="w-4 h-4" />
            <span className="tracking-wide">Disconnect Session</span>
          </button>
        </div>
      </div>

      {/* CORE VIEWPORT */}
      <div className="flex-1 flex flex-col h-full bg-white relative overflow-hidden">
        
        {viewMode === 'chat' && (
          <>
            <div className="w-full h-16 border-b border-zinc-100 px-8 flex items-center justify-between flex-shrink-0 bg-white/80 backdrop-blur-md z-10">
              <h1 className="text-sm font-semibold tracking-tight text-zinc-900">{activeThreadName || 'System Matrix'}</h1>
              <div className="flex items-center gap-2 bg-zinc-50 px-3 py-1.5 rounded-full border border-zinc-100 shadow-sm">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-sm shadow-emerald-400" />
                <span className="text-[10px] font-mono tracking-wider text-zinc-500 uppercase font-bold">Node Secure</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-6 md:px-0 scrollbar-none">
              <div className="max-w-2xl mx-auto pb-40 pt-8">
                {messages.length === 0 ? (
                  <div className="h-[55vh] flex flex-col items-center justify-center text-center px-4 select-none">
                    <div className="w-12 h-12 rounded-2xl bg-zinc-50 border border-zinc-100 flex items-center justify-center mb-5 shadow-sm">
                      <Shield className="w-5 h-5 text-zinc-400" />
                    </div>
                    <h3 className="text-sm font-medium text-zinc-900 tracking-tight">Sovereign Processing Pipeline</h3>
                    <p className="text-xs text-zinc-400 max-w-xs mt-1.5 leading-relaxed font-normal">
                      Decoupled workspace initialized. Direct API queries pass natively into your remote database engine layers.
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col">
                    {messages.map((msg, i) => {
                      const isUser = msg.role === 'user'
                      return (
                        <div key={i} className="py-7 flex items-start gap-6 border-b border-zinc-50 last:border-b-0">
                          <div className={`w-7 h-7 rounded-lg flex items-center justify-center shadow-sm border flex-shrink-0 select-none ${
                            isUser ? 'bg-zinc-50 border-zinc-200 text-zinc-600' : 'bg-gradient-to-br from-blue-50 to-indigo-50 border-blue-100 text-blue-600'
                          }`}>
                            {isUser ? <User className="w-3.5 h-3.5" /> : <Terminal className="w-3.5 h-3.5" />}
                          </div>
                          <div className="flex-1 text-zinc-800 text-[15px] leading-relaxed whitespace-pre-wrap pt-0.5 tracking-wide font-normal">
                            {msg.content}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
                {loading && (
                  <div className="py-7 flex items-start gap-6">
                    <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100 text-blue-600 flex items-center justify-center shadow-sm flex-shrink-0">
                      <Terminal className="w-3.5 h-3.5" />
                    </div>
                    <div className="flex-1 text-zinc-400 text-[14px] flex items-center gap-2.5 pt-1.5 font-normal select-none">
                      <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-500" />
                      <span className="tracking-wide">Computing execution matrices...</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            </div>

            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white/95 to-transparent pt-12 pb-8 px-6 md:px-0 flex-shrink-0 z-10">
              <form onSubmit={sendMessage} className="max-w-2xl mx-auto relative">
                <div className="flex items-center bg-white border border-zinc-200 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.06)] rounded-2xl hover:border-zinc-300 focus-within:border-zinc-400 focus-within:shadow-[0_12px_40px_-8px_rgba(0,0,0,0.09)] transition-all duration-200 px-4.5 py-2.5">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder={activeThreadId ? "Message your sovereign core..." : "Create a track to begin processing..."}
                    className="flex-1 bg-transparent text-zinc-900 text-[14px] py-2 pl-2 focus:outline-none placeholder-zinc-400 font-normal tracking-wide"
                    disabled={loading || !activeThreadId}
                  />
                  <button
                    type="submit"
                    disabled={!input.trim() || loading || !activeThreadId}
                    className={`p-2.5 rounded-xl transition-all duration-200 flex-shrink-0 shadow-sm ${
                      input.trim() && !loading && activeThreadId ? 'bg-zinc-950 text-white hover:bg-zinc-800' : 'bg-zinc-100 text-zinc-300 cursor-not-allowed shadow-none'
                    }`}
                  >
                    <Send className="w-3.5 h-3.5" />
                  </button>
                </div>
              </form>
            </div>
          </>
        )}

        {/* ADMIN CONFIGURATION VIEW */}
        {viewMode === 'admin' && (
          <div className="flex-1 flex flex-col h-full bg-zinc-50 overflow-y-auto">
            <div className="w-full h-16 border-b border-zinc-200/60 bg-white px-8 flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-4">
                <button onClick={() => setViewMode('chat')} className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 transition-colors">
                  <ArrowLeft className="w-4 h-4" />
                </button>
                <h1 className="text-sm font-semibold text-zinc-900 tracking-tight">System Configuration Console</h1>
              </div>
            </div>

            <div className="max-w-3xl w-full mx-auto px-8 py-8 flex flex-col gap-6">
              
              {/* Navigation Tabs Header */}
              <div className="flex gap-2 bg-zinc-200/60 p-1 rounded-xl self-start text-xs font-medium">
                <button 
                  onClick={() => { setAdminTab('pipeline'); setAdminMessage({type:'',text:''}); }}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${adminTab === 'pipeline' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-900'}`}
                >
                  <Sliders className="w-3.5 h-3.5" />
                  <span>⛓️ Step Router</span>
                </button>
                <button 
                  onClick={() => { setAdminTab('relays'); setAdminMessage({type:'',text:''}); }}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${adminTab === 'relays' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-900'}`}
                >
                  <Database className="w-3.5 h-3.5" />
                  <span>🌐 Server Relays</span>
                </button>
                <button 
                  onClick={() => { setAdminTab('vault'); setAdminMessage({type:'',text:''}); }}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${adminTab === 'vault' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-900'}`}
                >
                  <Key className="w-3.5 h-3.5" />
                  <span>🔑 API Vault</span>
                </button>
                <button 
                  onClick={() => { setAdminTab('security'); setAdminMessage({type:'',text:''}); }}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${adminTab === 'security' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-900'}`}
                >
                  <Lock className="w-3.5 h-3.5" />
                  <span>🔒 Access Gate</span>
                </button>
              </div>

              {adminMessage.text && (
                <div className={`p-4 rounded-xl border text-xs font-medium ${adminMessage.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-red-50 border-red-200 text-red-800'}`}>
                  {adminMessage.text}
                </div>
              )}

              {/* PANEL A: PIPELINE ROUTER */}
              {adminTab === 'pipeline' && (
                <form onSubmit={savePipeline} className="bg-white border border-zinc-200/80 rounded-2xl p-6 shadow-sm flex flex-col gap-5">
                  <div>
                    <h2 className="text-sm font-semibold text-zinc-900">Modify Operations Chain</h2>
                    <p className="text-xs text-zinc-400 mt-0.5">Reprogram foundational API orchestration loops dynamically stored inside SQL records.</p>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div className="flex flex-col gap-2">
                      <label className="font-semibold text-zinc-700">Sequence Order Position</label>
                      <input type="number" min="1" value={stepNum} onChange={(e) => setStepNum(parseInt(e.target.value) || 1)} className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400" />
                    </div>
                    <div className="flex flex-col gap-2">
                      <label className="font-semibold text-zinc-700">Display Step Name</label>
                      <input type="text" value={stepName} onChange={(e) => setStepName(e.target.value)} className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400" />
                    </div>
                    <div className="flex flex-col gap-2">
                      <label className="font-semibold text-zinc-700">API Envoy Prefix (e.g., 'openrouter' or 'gemini')</label>
                      <input type="text" value={providerId} onChange={(e) => setProviderId(e.target.value)} className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400" />
                    </div>
                    <div className="flex flex-col gap-2">
                      <label className="font-semibold text-zinc-700">Exact Model String Identifier</label>
                      <input type="text" value={modelId} onChange={(e) => setModelId(e.target.value)} className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400" />
                    </div>
                  </div>
                  <div className="flex flex-col gap-2 text-xs">
                    <label className="font-semibold text-zinc-700">System Prompt Directives</label>
                    <textarea value={sysPrompt} onChange={(e) => setSysPrompt(e.target.value)} rows={3} className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400 font-mono text-[11px]" />
                  </div>
                  <div className="flex flex-col gap-2 text-xs">
                    <label className="font-semibold text-zinc-700">Python Execution Logic (AST Protected)</label>
                    <textarea value={codeBody} onChange={(e) => setCodeBody(e.target.value)} rows={7} className="border border-zinc-200 rounded-xl px-3.5 py-3 bg-zinc-950 text-zinc-200 font-mono text-[12px] leading-relaxed focus:outline-none focus:border-zinc-700" />
                  </div>
                  <button type="submit" className="bg-zinc-950 text-white text-xs font-semibold py-3 px-4 rounded-xl hover:bg-zinc-800 transition-colors self-end shadow-sm">
                    Save Operational Directives
                  </button>
                </form>
              )}

              {/* PANEL B: DATABASE RELAYS */}
              {adminTab === 'relays' && (
                <form onSubmit={saveRelays} className="bg-white border border-zinc-200/80 rounded-2xl p-6 shadow-sm flex flex-col gap-5">
                  <div>
                    <h2 className="text-sm font-semibold text-zinc-900">SQL Cloud Server Allocation Map</h2>
                    <p className="text-xs text-zinc-400 mt-0.5">Dynamically adjust transactional boundaries and database targets across cloud servers.</p>
                  </div>
                  <div className="flex flex-col gap-2 text-xs">
                    <label className="font-semibold text-zinc-700">Metadata Threads SQL Target URI</label>
                    <input type="text" value={threadsUrl} onChange={(e) => setThreadsUrl(e.target.value)} placeholder="postgresql://..." className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400 font-mono text-[11px]" />
                  </div>
                  <div className="flex flex-col gap-2 text-xs">
                    <label className="font-semibold text-zinc-700">Heavy Log Transaction SQL Target URI</label>
                    <input type="text" value={messagesUrl} onChange={(e) => setMessagesUrl(e.target.value)} placeholder="postgresql://..." className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400 font-mono text-[11px]" />
                  </div>
                  <button type="submit" className="bg-zinc-950 text-white text-xs font-semibold py-3 px-4 rounded-xl hover:bg-zinc-800 transition-colors self-end shadow-sm">
                    Commit Cluster Routing Changes
                  </button>
                </form>
              )}

              {/* NEW PANEL C: HOT-SWAPPABLE API KEY VAULT CONTROL */}
              {adminTab === 'vault' && (
                <div className="flex flex-col gap-6">
                  {/* Key Injection Form */}
                  <form onSubmit={saveVaultKey} className="bg-white border border-zinc-200/80 rounded-2xl p-6 shadow-sm flex flex-col gap-4">
                    <div>
                      <h2 className="text-sm font-semibold text-zinc-900">Inject Platform Authorization Token</h2>
                      <p className="text-xs text-zinc-400 mt-0.5">Link an active API key directly to a specific dynamic provider string prefix.</p>
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-xs items-end">
                      <div className="flex flex-col gap-2 col-span-1">
                        <label className="font-semibold text-zinc-700">Envoy Identifier (Lowercase)</label>
                        <input 
                          type="text" 
                          required
                          value={vaultProviderInput} 
                          onChange={(e) => setVaultProviderInput(e.target.value)} 
                          placeholder="e.g., openrouter" 
                          className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400 font-mono text-[11px]" 
                        />
                      </div>
                      <div className="flex flex-col gap-2 col-span-2">
                        <label className="font-semibold text-zinc-700">Secret Token Secret String</label>
                        <input 
                          type="password" 
                          required
                          value={vaultKeyInput} 
                          onChange={(e) => setVaultKeyInput(e.target.value)} 
                          placeholder="sk-or-v1-..." 
                          className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400 font-mono text-[11px]" 
                        />
                      </div>
                    </div>
                    <button type="submit" className="bg-zinc-950 text-white text-xs font-semibold py-2.5 px-4 rounded-xl hover:bg-zinc-800 transition-colors self-end shadow-sm">
                      Save Token Mapping
                    </button>
                  </form>

                  {/* Registered Keys List View */}
                  <div className="bg-white border border-zinc-200/80 rounded-2xl p-6 shadow-sm flex flex-col gap-3">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-1">Active Vault Records</h3>
                    {vaultKeys.length === 0 ? (
                      <p className="text-xs text-zinc-500 italic">No keys stored inside database. System is entirely dependent on Render background env maps.</p>
                    ) : (
                      <div className="flex flex-col gap-2">
                        {vaultKeys.map((k) => (
                          <div key={k.provider_identifier} className="flex items-center justify-between p-3 rounded-xl border border-zinc-100 bg-zinc-50/50 text-xs font-mono">
                            <div className="flex items-center gap-4">
                              <span className="font-semibold text-zinc-800 bg-zinc-200/60 px-2 py-1 rounded lowercase">{k.provider_identifier}</span>
                              <span className="text-zinc-400 tracking-wider">{k.api_key}</span>
                            </div>
                            <button 
                              onClick={() => deleteVaultKey(k.provider_identifier)}
                              className="p-1.5 rounded-lg text-zinc-400 hover:bg-red-50 hover:text-red-500 transition-colors"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* PANEL D: ACCESS MANAGEMENT SECURITY GATE */}
              {adminTab === 'security' && (
                <form onSubmit={changeCredentials} className="bg-white border border-zinc-200/80 rounded-2xl p-6 shadow-sm flex flex-col gap-5">
                  <div>
                    <h2 className="text-sm font-semibold text-zinc-900">Master Identity Management</h2>
                    <p className="text-xs text-zinc-400 mt-0.5">Overwrite administrative keys stored inside system SQL data logs.</p>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div className="flex flex-col gap-2">
                      <label className="font-semibold text-zinc-700">New Cluster Username</label>
                      <input type="text" required value={newUsername} onChange={(e) => setNewUsername(e.target.value)} placeholder="Minimum 3 characters..." className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400" />
                    </div>
                    <div className="flex flex-col gap-2">
                      <label className="font-semibold text-zinc-700">New Master Password</label>
                      <input type="password" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Minimum 6 characters..." className="border border-zinc-200 rounded-xl px-3 py-2.5 bg-zinc-50/50 focus:outline-none focus:border-zinc-400" />
                    </div>
                  </div>
                  <button type="submit" className="bg-zinc-950 text-white text-xs font-semibold py-3 px-4 rounded-xl hover:bg-zinc-800 transition-colors self-end shadow-sm">
                    Update Administrative Master Keys
                  </button>
                </form>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
