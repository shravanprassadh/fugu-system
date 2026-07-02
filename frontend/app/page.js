"use client"

import React, { useState, useEffect, useRef } from 'react'
import { MessageSquare, Plus, Send, Settings, Shield, RefreshCw, Sparkles, User, Terminal, Database, Sliders, ArrowLeft } from 'lucide-react'

export default function Workspace() {
  // Global View States
  const [viewMode, setViewMode] = useState('chat') // 'chat' or 'admin'
  const [adminTab, setAdminTab] = useState('pipeline') // 'pipeline' or 'relays'
  
  // Data State Arrays
  const [threads, setThreads] = useState([])
  const [activeThreadId, setActiveThreadId] = useState(null)
  const [activeThreadName, setActiveThreadName] = useState('')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [newThreadName, setNewThreadName] = useState('')
  
  // Administrative Inputs Form State
  const [stepNum, setStepNum] = useState(1)
  const [stepName, setStepName] = useState('Sovereign Auto-Core')
  const [providerId, setProviderId] = useState('openrouter')
  const [modelId, setModelId] = useState('openrouter/free')
  const [sysPrompt, setSysPrompt] = useState('You are a helpful assistant.')
  const [codeBody, setCodeBody] = useState(`def execute_step(payload, system_prompt, model_string, api_key):\n    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)\n    response = client.chat.completions.create(\n        model=model_string,\n        messages=[\n            {"role": "system", "content": system_prompt},\n            {"role": "user", "content": payload}\n        ]\n    )\n    return response.choices[0].message.content`)
  
  const [threadsUrl, setThreadsUrl] = useState('')
  const [messagesUrl, setMessagesUrl] = useState('')
  const [adminMessage, setAdminMessage] = useState({ type: '', text: '' })

  const messagesEndRef = useRef(null)
  const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || ''

  useEffect(() => {
    fetchThreads()
  }, [])

  useEffect(() => {
    if (activeThreadId && viewMode === 'chat') {
      fetchMessages(activeThreadId)
    }
  }, [activeThreadId, viewMode])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Core Synchronizations
  const fetchThreads = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/threads`)
      const data = await res.json()
      if (data.threads && data.threads.length > 0) {
        setThreads(data.threads)
        if (!activeThreadId) {
          setActiveThreadId(data.threads[0].id)
          setActiveThreadName(data.threads[0].name)
        }
      }
    } catch (err) {
      console.error("Failed fetching log context layers:", err)
    }
  }

  const fetchMessages = async (threadId) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/threads/${threadId}/messages`)
      const data = await res.json()
      if (data.messages) setMessages(data.messages)
    } catch (err) {
      console.error("Failed pulling conversation vault:", err)
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
    } catch (err) {
      console.error("Administrative call rejected by server network:", err)
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
      setNewThreadName('')
      await fetchThreads()
    } catch (err) {
      console.error("Failed syncing track register:", err)
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
        throw new Error(errData.detail || "Pipeline sequence failure")
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
        throw new Error(err.detail || "Ast parameters invalid.")
      }
      setAdminMessage({ type: 'success', text: 'Operational pipeline directives updated successfully.' })
    } catch (err) {
      setAdminMessage({ type: 'error', text: `Failed committing parameters: ${err.message}` })
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
      if (!res.ok) throw new Error("Server rejected cluster relay updates.")
      setAdminMessage({ type: 'success', text: 'Cloud relay paths updated successfully.' })
    } catch (err) {
      setAdminMessage({ type: 'error', text: err.message })
    }
  }

  return (
    <div className="flex h-screen w-screen bg-white overflow-hidden font-sans antialiased text-zinc-900">
      
      {/* ========================================== */}
      {/* CONTROL SIDEBAR DESIGN PARADIGM            */}
      {/* ========================================== */}
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

        {/* Conversation Tracks Stack */}
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
                className={`w-full flex items-center justify-between px-3.5 py-3 rounded-xl text-xs font-medium text-left transition-all duration-200 group ${
                  isActive ? 'bg-zinc-900 text-zinc-100 border border-zinc-800/60 shadow-inner' : 'text-zinc-400 hover:bg-zinc-900/40 hover:text-zinc-200'
                }`}
              >
                <div className="flex items-center gap-3 truncate mr-2">
                  <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 transition-colors ${isActive ? 'text-blue-400' : 'text-zinc-500 group-hover:text-zinc-400'}`} />
                  <span className="truncate tracking-wide">{t.name}</span>
                </div>
                {isActive && <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shadow-sm shadow-blue-400" />}
              </button>
            )
          })}
        </div>

        {/* Panel Anchor Navigation Button */}
        <div className="p-4 border-t border-zinc-900 bg-zinc-950/80">
          <button 
            onClick={() => {
              setViewMode('admin')
              setAdminMessage({ type: '', text: '' })
              fetchAdminConfig()
            }}
            className={`w-full flex items-center gap-3 px-3.5 py-3 rounded-xl text-xs font-medium transition-all duration-200 border ${
              viewMode === 'admin' 
                ? 'bg-blue-600 text-white border-blue-500 shadow-md shadow-blue-600/10' 
                : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200 border-transparent hover:border-zinc-800/40'
            }`}
          >
            <Settings className={`w-4 h-4 ${viewMode === 'admin' ? 'text-white' : 'text-zinc-500'}`} />
            <span className="tracking-wide">Cluster Configuration</span>
          </button>
        </div>
      </div>

      {/* ========================================== */}
      {/* INTERACTIVE COMPILATION MAIN WORKSPACE     */}
      {/* ========================================== */}
      <div className="flex-1 flex flex-col h-full bg-white relative overflow-hidden">
        
        {/* VIEW 1: PREMIUM CONVERSATION ENGINE CANVAS */}
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
                    placeholder="Message your sovereign core..."
                    className="flex-1 bg-transparent text-zinc-900 text-[14px] py-2 pl-2 focus:outline-none placeholder-zinc-400 font-normal tracking-wide"
                    disabled={loading}
                  />
                  <button
                    type="submit"
                    disabled={!input.trim() || loading}
                    className={`p-2.5 rounded-xl transition-all duration-200 flex-shrink-0 shadow-sm ${
                      input.trim() && !loading ? 'bg-zinc-950 text-white hover:bg-zinc-800' : 'bg-zinc-100 text-zinc-300 cursor-not-allowed shadow-none'
                    }`}
                  >
                    <Send className="w-3.5 h-3.5" />
                  </button>
                </div>
              </form>
            </div>
          </>
        )}

        {/* VIEW 2: COMPOSABLE CLUSTER CONTROL STATION */}
        {viewMode === 'admin' && (
          <div className="flex-1 flex flex-col h-full bg-zinc-50 overflow-y-auto">
            
            {/* Admin Header Shell */}
            <div className="w-full h-16 border-b border-zinc-200/60 bg-white px-8 flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-4">
                <button onClick={() => setViewMode('chat')} className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 transition-colors">
                  <ArrowLeft className="w-4 h-4" />
                </button>
                <h1 className="text-sm font-semibold text-zinc-900 tracking-tight">System Configuration Console</h1>
              </div>
            </div>

            {/* Admin Central Content Grid */}
            <div className="max-w-3xl w-full mx-auto px-8 py-8 flex flex-col gap-6">
              
              {/* Tab Selector Links */}
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
              </div>

              {/* Server Responses System Logs */}
              {adminMessage.text && (
                <div className={`p-4 rounded-xl border text-xs font-medium ${adminMessage.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-red-50 border-red-200 text-red-800'}`}>
                  {adminMessage.text}
                </div>
              )}

              {/* SUB-PANEL A: STEP ROUTER LOGIC FORM */}
              {adminTab === 'pipeline' && (
                <form onSubmit={savePipeline} className="bg-white border border-zinc-200/80 rounded-2xl p-6 shadow-sm flex flex-col gap-5">
                  <div>
                    <h2 className="text-sm font-semibold text-zinc-900">Modify Operations Chain</h2>
                    <p className="text-xs text-zinc-400 mt-0.5">Reprogram the foundational API orchestration loops dynamically stored in SQL database blocks.</p>
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
                      <label className="font-semibold text-zinc-700">API Envoy Prefix</label>
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

              {/* SUB-PANEL B: SQL CLOUD ROUTING MAP */}
              {adminTab === 'relays' && (
                <form onSubmit={saveRelays} className="bg-white border border-zinc-200/80 rounded-2xl p-6 shadow-sm flex flex-col gap-5">
                  <div>
                    <h2 className="text-sm font-semibold text-zinc-900">SQL Cloud Server Allocation Map</h2>
                    <p className="text-xs text-zinc-400 mt-0.5">Dynamically adjust the transactional boundaries. Direct data traffic to specific remote database endpoints.</p>
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

            </div>
          </div>
        )}

      </div>
    </div>
  )
}
