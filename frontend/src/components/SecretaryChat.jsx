import dayjs from 'dayjs'
import { ArrowLeft, Search, Send } from 'lucide-react'
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { getSecretaryMessages, getSecretaryOpening, searchSecretaryMessages, sendSecretaryChat } from '../api'
import SecretaryAvatar from './SecretaryAvatar'

function Bubble({ message, mood = 'idle' }) {
  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && <SecretaryAvatar size={28} mood={mood} className="mr-2 mt-1" />}
      <div
        className={`max-w-[82%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'rounded-br-md bg-primary text-white'
            : 'rounded-bl-md bg-slate-100 text-slate-800'
        }`}
      >
        {message.content}
        <div className={`mt-1 text-[10px] ${isUser ? 'text-white/60' : 'text-slate-400'}`}>
          {dayjs(message.created_at).format('HH:mm')}
        </div>
      </div>
    </div>
  )
}

const SecretaryChat = forwardRef(function SecretaryChat({ onTaskParsed }, ref) {
  const [messages, setMessages] = useState([])
  const [suggestions, setSuggestions] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [happy, setHappy] = useState(false)
  const [searchMode, setSearchMode] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const scrollRef = useRef(null)
  const happyTimer = useRef(null)

  const runSearch = async () => {
    const q = searchQuery.trim()
    if (!q) return
    setSearching(true)
    try {
      const result = await searchSecretaryMessages(q)
      setSearchResults(result.messages || [])
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const exitSearch = () => {
    setSearchMode(false)
    setSearchQuery('')
    setSearchResults(null)
  }

  const celebrate = () => {
    setHappy(true)
    window.clearTimeout(happyTimer.current)
    happyTimer.current = window.setTimeout(() => setHappy(false), 2000)
  }

  useImperativeHandle(ref, () => ({
    addLocalSecretaryMessage(content) {
      setMessages((current) => [
        ...current,
        { id: `local-${Date.now()}`, role: 'secretary', content, created_at: new Date().toISOString() },
      ])
      celebrate()
    },
  }))

  useEffect(() => {
    let active = true
    const init = async () => {
      try {
        const history = await getSecretaryMessages(30)
        if (!active) return
        setMessages(history.messages || [])
        const opening = await getSecretaryOpening()
        if (!active) return
        if (opening.message) {
          setMessages((current) => [
            ...current,
            {
              id: opening.message_id || `opening-${Date.now()}`,
              role: 'secretary',
              content: opening.message,
              created_at: new Date().toISOString(),
            },
          ])
        }
        setSuggestions(opening.suggestions || [])
      } catch {
        if (active) {
          setMessages((current) =>
            current.length
              ? current
              : [{ id: 'err', role: 'secretary', content: '我在，随时吩咐。（对话记录暂时没加载出来）', created_at: new Date().toISOString() }],
          )
        }
      } finally {
        if (active) setLoading(false)
      }
    }
    init()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending, loading])

  const send = async (text) => {
    const value = (text ?? input).trim()
    if (!value || sending) return
    setInput('')
    setSuggestions([])
    setSending(true)
    setMessages((current) => [
      ...current,
      { id: `u-${Date.now()}`, role: 'user', content: value, created_at: new Date().toISOString() },
    ])
    try {
      const result = await sendSecretaryChat(value)
      if (result.reply) {
        setMessages((current) => [
          ...current,
          { id: `s-${Date.now()}`, role: 'secretary', content: result.reply, created_at: new Date().toISOString() },
        ])
      }
      if (result.intent === 'create_task' && result.parsed) {
        onTaskParsed?.(result.parsed)
      }
    } catch {
      setMessages((current) => [
        ...current,
        { id: `e-${Date.now()}`, role: 'secretary', content: '刚才这句没发出去，请再试一次。', created_at: new Date().toISOString() },
      ])
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="flex flex-col rounded-xl2 border border-slate-200/80 bg-white shadow-card">
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-2.5">
        {searchMode ? (
          <>
            <button type="button" onClick={exitSearch} className="text-slate-400 transition hover:text-slate-600">
              <ArrowLeft size={16} />
            </button>
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && runSearch()}
              autoFocus
              placeholder="搜历史对话，比如：报价"
              className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400"
            />
            <button
              type="button"
              onClick={runSearch}
              disabled={searching || !searchQuery.trim()}
              className="text-sm font-medium text-primary disabled:opacity-50"
            >
              {searching ? '搜索中...' : '搜索'}
            </button>
          </>
        ) : (
          <>
            <span className="text-sm font-bold text-slate-800">小e · AI 秘书</span>
            <button
              type="button"
              onClick={() => setSearchMode(true)}
              className="ml-auto text-slate-400 transition hover:text-slate-600"
              title="搜索历史对话"
            >
              <Search size={16} />
            </button>
          </>
        )}
      </div>

      {searchMode && searchResults !== null && (
        <div className="max-h-[360px] space-y-2 overflow-y-auto p-4">
          {searchResults.length === 0 && (
            <p className="text-sm text-slate-400">没搜到相关记录，换个词试试。</p>
          )}
          {searchResults.map((message) => (
            <div key={message.id} className="rounded-xl bg-slate-50 px-3.5 py-2.5 ring-1 ring-slate-100">
              <p className="text-sm text-slate-800">{message.content}</p>
              <p className="mt-1 text-[11px] text-slate-400">
                {message.role === 'user' ? '你' : '小e'} · {dayjs(message.created_at).format('M月D日 HH:mm')}
              </p>
            </div>
          ))}
        </div>
      )}

      <div
        ref={scrollRef}
        className={`max-h-[420px] min-h-[220px] space-y-3 overflow-y-auto p-4 ${searchMode && searchResults !== null ? 'hidden' : ''}`}
      >
        {loading && <p className="text-sm text-slate-400">秘书正在整理今天的情况...</p>}
        {!loading && messages.length === 0 && (
          <p className="text-sm text-slate-400">跟我说点什么吧，记待办、问建议都行。</p>
        )}
        {messages.map((message, index) => {
          const isLastSecretary =
            message.role === 'secretary' &&
            index === messages.length - 1
          return (
            <Bubble
              key={message.id}
              message={message}
              mood={happy && isLastSecretary ? 'happy' : 'idle'}
            />
          )
        })}
        {sending && (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <SecretaryAvatar size={28} mood="thinking" />
            秘书思考中...
          </div>
        )}
      </div>

      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2 px-4 pb-2">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => send(suggestion)}
              className="rounded-full border border-brand-100 bg-primary-soft px-3 py-1.5 text-xs font-medium text-primary-deep transition hover:bg-brand-100"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault()
          send()
        }}
        className="flex items-end gap-2 border-t border-slate-100 p-3"
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              send()
            }
          }}
          rows={1}
          placeholder="记待办、问建议、汇报进展，直接说人话"
          className="max-h-28 min-w-0 flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50/70 px-3.5 py-2.5 text-sm outline-none transition focus:border-primary focus:bg-white focus:ring-2 focus:ring-primary/10"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="inline-flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-primary text-white shadow-[0_6px_14px_rgba(79,70,229,0.30)] transition hover:bg-primary-deep disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
        >
          <Send size={17} />
        </button>
      </form>
    </section>
  )
})

export default SecretaryChat
