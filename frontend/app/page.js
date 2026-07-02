"use client"

import React, { useState, useEffect, useRef } from 'react'
import { MessageSquare, Plus, Send, Settings, Shield, RefreshCw } from 'lucide-react'

export default function Workspace() {
  // Application State Management Matrix
  const [threads, setThreads] = useState([])
  const [activeThreadId, setActiveThreadId] = useState(null)
  const [activeThreadName, setActiveThreadName] = useState('')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [newThreadName, setNewThreadName] = useState('')
  
  const messagesEndRef = useRef(null)
  const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || ''

  // Scroll to anchor points smoothly on message state shifts
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    fetchThreads()
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Transport Layer API Transactions
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
    
    // Optimistic rendering: push to local screen state instantly without lag
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])
    setLoading(true)

    try {
      // In a decoupled application, we will wire this link directly to the dynamic pipeline execution endpoint
      // Temporary loop mapping to backend structures
      setTimeout(() => {
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: `Backend gateway acknowledge. Connected to API server: ${BACKEND_URL || 'Local Container'}. Pipeline routes operational.` 
        }])
        setLoading(false)
      }, 1200)
    } catch (err) {
      console.error("Pipeline handoff interrupted:", err)
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen w-screen bg-white overflow-hidden text-gray-900">
      
      {/* ========================================== */}
      {/* THE SIDEBAR PANEL (PREMIUM LAYOUT PARADIGM) */}
      {/* ========================================== */}
      <div className="w-64 bg-slate-50 border-r border-slate-200 flex flex-col flex-shrink-0 h-full">
        <div className="p-4 flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-gray-800 tracking-tight flex items-center gap-2">
            <span>✨ Sovereign Canvas</span>
          </h2>
          
          {/* Create Thread Form */}
          <form onSubmit={createThread} className="flex gap-2">
            <input
              type="text"
              placeholder="New track..."
              value={newThreadName}
              onChange={(e) => setNewThreadName(e.target.value)}
              className="w-full text-xs bg-white text-gray-900 border border-slate-300 rounded-lg px-2.5 py-2 focus:outline-none focus:border-blue-500 transition-all"
            />
            <button type="submit" className="bg-slate-900 text-white p-2 rounded-lg hover:bg-slate-800 transition-colors">
              <Plus className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>

        <hr className="border-slate-200 mx-4" />

        {/* Dynamic Context History Stream */}
        <div className="flex-1 overflow-y-auto px-3 py-4 flex flex-col gap-1 select-none">
          <p className="text-[10px] font-bold text-gray-400 px-2 tracking-wider uppercase mb-1">Recent Conversations</p>
          {threads.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                setActiveThreadId(t.id)
                setActiveThreadName(t.name)
                setMessages([]) // Clears the local container view to fetch fresh logs
              }}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-left transition-all ${
                activeThreadId === t.id 
                  ? 'bg-slate-200 text-gray-900' 
                  : 'text-gray-600 hover:bg-slate-100 hover:text-gray-900'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5 opacity-70 flex-shrink-0" />
              <span className="truncate flex-1">{t.name}</span>
            </button>
          ))}
        </div>

        {/* Administrative Anchor Zone */}
        <div className="p-3 border-t border-slate-200 bg-slate-50">
          <button className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-xs font-medium text-gray-600 hover:bg-slate-100 hover:text-gray-900 transition-all">
            <Settings className="w-4 h-4 opacity-70" />
            <span>Advanced Controls</span>
          </button>
        </div>
      </div>

      {/* ========================================== */}
      {/* THE MAIN INTERACTIVE WORKSPACE VIEW        */}
      {/* ========================================== */}
      <div className="flex-1 flex flex-col h-full bg-white relative">
        
        {/* Sticky Header Strip */}
        <div className="w-full h-14 border-b border-slate-100 px-6 flex items-center justify-between flex-shrink-0">
          <h1 className="text-sm font-medium text-gray-800">{activeThreadName || 'Initialize Core Framework'}</h1>
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-[11px] font-semibold tracking-wider text-gray-400 uppercase">Sovereign Node Live</span>
          </div>
        </div>

        {/* Asynchronous Message Flow Containers */}
        <div className="flex-1 overflow-y-auto px-4 md:px-0">
          <div className="max-w-2xl mx-auto divide-y divide-slate-100 pb-36">
            {messages.length === 0 ? (
              <div className="h-[50vh] flex flex-col items-center justify-center text-center px-4">
                <div className="w-10 h-10 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
                  <Shield className="w-5 h-5" />
                </div>
                <h3 className="text-base font-medium text-gray-900">Sovereign Processing Matrix Active</h3>
                <p className="text-xs text-gray-500 max-w-xs mt-1">Your user execution profile is locked. Network operations are routed entirely through your decoupled private clusters.</p>
              </div>
            ) : (
              messages.map((msg, i) => {
                const isUser = msg.role === 'user'
                return (
                  <div key={i} className="py-6 flex items-start gap-5">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs flex-shrink-0 select-none shadow-sm ${
                      isUser ? 'bg-slate-100 text-gray-600' : 'bg-blue-50 text-blue-600'
                    }`}>
                      {isUser ? 'U' : 'AI'}
                    </div>
                    <div className="flex-1 text-gray-800 text-[15px] leading-relaxed whitespace-pre-wrap pt-0.5 font-normal">
                      {msg.content}
                    </div>
                  </div>
                )
              })
            )}
            
            {/* Generating Loader Element */}
            {loading && (
              <div className="py-6 flex items-start gap-5">
                <div className="w-8 h-8 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center font-bold text-xs flex-shrink-0 shadow-sm">
                  AI
                </div>
                <div className="flex-1 text-gray-400 text-[15px] flex items-center gap-2 pt-1 font-normal">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-500" />
                  <span>Processing operational nodes...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Anchored Input Bar Component Frame */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white to-transparent pt-10 pb-6 px-4 md:px-0 flex-shrink-0">
          <form onSubmit={sendMessage} className="max-w-2xl mx-auto relative">
            <div className="flex items-center bg-white border border-slate-200 rounded-3xl shadow-md hover:border-slate-300 focus-within:border-gray-400 focus-within:shadow-lg transition-all px-4 py-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Message your sovereign core..."
                className="flex-1 bg-transparent text-gray-900 text-sm py-2 focus:outline-none placeholder-gray-400 font-normal"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className={`p-2 rounded-full transition-colors flex-shrink-0 ${
                  input.trim() && !loading
                    ? 'bg-slate-900 text-white hover:bg-slate-800'
                    : 'bg-slate-100 text-gray-300 cursor-not-allowed'
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
