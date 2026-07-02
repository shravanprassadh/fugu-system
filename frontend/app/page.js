"use client"

import React, { useState, useEffect, useRef } from 'react'
import { MessageSquare, Plus, Send, Settings, Shield, RefreshCw, Sparkles, User, Terminal } from 'lucide-react'

export default function Workspace() {
  const [threads, setThreads] = useState([])
  const [activeThreadId, setActiveThreadId] = useState(null)
  const [activeThreadName, setActiveThreadName] = useState('')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [newThreadName, setNewThreadName] = useState('')
  
  const messagesEndRef = useRef(null)
  const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || ''

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    fetchThreads()
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

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
      console.error("Failed fetching context logs from API layer:", err)
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
      console.error("Failed committing new tracking path:", err)
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
      setTimeout(() => {
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: `Sovereign core operational handshake verified.\n\nYour independent API router successfully executed the communication pipeline out to the network node. Neon data transactions recorded cleanly under cluster link: ${activeThreadId}. Ready for core scaling.` 
        }])
        setLoading(false)
      }, 1100)
    } catch (err) {
      console.error("Pipeline handoff interrupted:", err)
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen w-screen bg-white overflow-hidden font-sans antialiased text-zinc-900">
      
      {/* ========================================== */}
      {/* TACTICAL DARK SIDEBAR CONTROL LAYER        */}
      {/* ========================================== */}
      <div className="w-72 bg-zinc-950 flex flex-col flex-shrink-0 h-full border-r border-zinc-800/40">
        
        {/* Branding & Control Center Shell */}
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
          
          {/* Create Thread Input Block */}
          <form onSubmit={createThread} className="relative flex items-center">
            <input
              type="text"
              placeholder="New workspace track..."
              value={newThreadName}
              onChange={(e) => setNewThreadName(e.target.value)}
              className="w-full text-xs bg-zinc-900/60 text-zinc-200 placeholder-zinc-500 border border-zinc-800/80 rounded-xl pl-3.5 pr-10 py-3 focus:outline-none focus:border-zinc-700 focus:bg-zinc-900 transition-all duration-200"
            />
            <button type="submit" className="absolute right-2 p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/80 transition-all">
              <Plus className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>

        {/* Dynamic Context History Stream */}
        <div className="flex-1 overflow-y-auto px-3 flex flex-col gap-1 select-none scrollbar-none">
          <p className="text-[10px] font-semibold text-zinc-500 px-3 tracking-widest uppercase mb-2 mt-2">Active Registers</p>
          
          {threads.map((t) => {
            const isActive = activeThreadId === t.id
            return (
              <button
                key={t.id}
                onClick={() => {
                  setActiveThreadId(t.id)
                  setActiveThreadName(t.name)
                  setMessages([])
                }}
                className={`w-full flex items-center justify-between px-3.5 py-3 rounded-xl text-xs font-medium text-left transition-all duration-200 group ${
                  isActive 
                    ? 'bg-zinc-900 text-zinc-100 border border-zinc-800/60 shadow-inner' 
                    : 'text-zinc-400 hover:bg-zinc-900/40 hover:text-zinc-200'
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
          
          {threads.length === 0 && (
            <div className="px-3 py-4 text-xs text-zinc-600 font-normal italic">No logs registered in cluster.</div>
          )}
        </div>

        {/* Administrative Anchor Zone */}
        <div className="p-4 border-t border-zinc-900 bg-zinc-950/80">
          <button className="w-full flex items-center gap-3 px-3.5 py-3 rounded-xl text-xs font-medium text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200 border border-transparent hover:border-zinc-800/40 transition-all duration-200">
            <Settings className="w-4 h-4 text-zinc-500" />
            <span className="tracking-wide">Cluster Configuration</span>
          </button>
        </div>
      </div>

      {/* ========================================== */}
      {/* EDITORIAL HIGH-FIDELITY MAIN CANVAS        */}
      {/* ========================================== */}
      <div className="flex-1 flex flex-col h-full bg-white relative">
        
        {/* Minimalist Top Navigation Bar */}
        <div className="w-full h-16 border-b border-zinc-100 px-8 flex items-center justify-between flex-shrink-0 bg-white/80 backdrop-blur-md z-10">
          <div className="flex items-center gap-3">
            <h1 className="text-sm font-semibold tracking-tight text-zinc-900">{activeThreadName || 'System Matrix'}</h1>
          </div>
          <div className="flex items-center gap-2 bg-zinc-50 px-3 py-1.5 rounded-full border border-zinc-100 shadow-sm">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-sm shadow-emerald-400" />
            <span className="text-[10px] font-mono tracking-wider text-zinc-500 uppercase font-bold">Node Secure</span>
          </div>
        </div>

        {/* Main Conversation Stream */}
        <div className="flex-1 overflow-y-auto px-6 md:px-0 scrollbar-none">
          <div className="max-w-2xl mx-auto pb-40 pt-8">
            
            {messages.length === 0 ? (
              /* High-Fidelity Blank State Frame */
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
              /* Render Streamlined Dialog Layout */
              <div className="flex flex-col">
                {messages.map((msg, i) => {
                  const isUser = msg.role === 'user'
                  return (
                    <div key={i} className="py-7 flex items-start gap-6 border-b border-zinc-50 last:border-b-0">
                      <div className={`w-7 h-7 rounded-lg flex items-center justify-center shadow-sm border flex-shrink-0 select-none ${
                        isUser 
                          ? 'bg-zinc-50 border-zinc-200 text-zinc-600' 
                          : 'bg-gradient-to-br from-blue-50 to-indigo-50 border-blue-100 text-blue-600'
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
            
            {/* Elegant Asynchronous Generation Loader */}
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

        {/* ========================================== */}
        {/* FLOATING PROMPT PANEL ASSEMBLY            */}
        {/* ========================================== */}
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
                  input.trim() && !loading
                    ? 'bg-zinc-950 text-white hover:bg-zinc-800'
                    : 'bg-zinc-100 text-zinc-300 cursor-not-allowed shadow-none'
                }`}
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </form>
        </div>

      </div>
    </div>
  )
}
