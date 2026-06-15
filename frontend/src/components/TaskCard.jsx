import dayjs from 'dayjs'
import { Check, PlayCircle, Send, Trash2 } from 'lucide-react'
import { useState } from 'react'

const badgeClass = {
  工作: 'bg-blue-50 text-blue-700',
  财务: 'bg-emerald-50 text-emerald-700',
  生活: 'bg-amber-50 text-amber-700',
  灵感: 'bg-purple-50 text-purple-700',
  学习: 'bg-teal-50 text-teal-700',
  其他: 'bg-slate-100 text-slate-600',
}

const statusText = {
  pending: '待处理',
  in_progress: '进行中',
  waiting_response: '等回复',
  blocked: '受阻',
  done: '已完成',
  cancelled: '已取消',
}

const statusClass = {
  pending: 'bg-slate-100 text-slate-600',
  in_progress: 'bg-indigo-50 text-primary-deep',
  waiting_response: 'bg-amber-50 text-amber-700',
  blocked: 'bg-rose-50 text-rose-700',
  done: 'bg-slate-100 text-slate-500',
  cancelled: 'bg-slate-100 text-slate-500',
}

export default function TaskCard({ task, onComplete, onStart, onDelete, onReply, busy }) {
  const [reply, setReply] = useState('')
  const isDone = task.status === 'done'
  const isInProgress = task.status === 'in_progress'
  const isTerminal = ['done', 'cancelled'].includes(task.status)

  return (
    <article className="rounded-xl2 border border-slate-200/80 bg-white p-4 shadow-soft transition hover:-translate-y-px hover:shadow-card">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
            badgeClass[task.category] || badgeClass.其他
          }`}
        >
          {task.category || '其他'}
        </span>
        <span
          className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
            statusClass[task.status] || statusClass.pending
          }`}
        >
          {statusText[task.status] || task.status || '待处理'}
        </span>
        <span className="ml-auto text-xs font-semibold text-slate-400">
          优先级 {task.priority_level || task.priority || 'B'}
        </span>
      </div>
      <h3
        className={`mt-3 text-[15px] font-semibold ${
          isDone ? 'text-slate-400 line-through' : 'text-slate-900'
        }`}
      >
        {task.content}
      </h3>
      {task.goal && <p className="mt-2 text-sm text-slate-600">目标：{task.goal}</p>}
      {task.related_person && <p className="mt-1 text-sm text-slate-500">相关人：{task.related_person}</p>}
      <p className="mt-2 text-sm text-slate-500">
        {task.remind_time ? dayjs(task.remind_time).format('M月D日 HH:mm') : '未设置提醒时间'}
      </p>
      {task.next_follow_time && (
        <p className="mt-1 text-sm text-slate-500">
          下次跟进：{dayjs(task.next_follow_time).format('M月D日 HH:mm')}
        </p>
      )}
      {task.progress_note && (
        <p className="mt-2.5 rounded-xl border-l-[3px] border-primary bg-slate-50 px-3 py-2 text-sm text-slate-600">
          进展：{task.progress_note}
        </p>
      )}
      {!isTerminal && onReply && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={async (event) => {
            event.preventDefault()
            if (!reply.trim()) return
            await onReply(task.id, reply.trim())
            setReply('')
          }}
        >
          <input
            value={reply}
            onChange={(event) => setReply(event.target.value)}
            placeholder="回复进展，例如：对方下周给报价"
            className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/10"
          />
          <button
            type="submit"
            disabled={busy || !reply.trim()}
            className="inline-flex items-center gap-1 rounded-xl bg-primary px-3.5 py-2 text-sm text-white transition hover:bg-primary-deep disabled:opacity-60"
          >
            <Send size={15} />
            回复
          </button>
        </form>
      )}
      <div className="mt-4 flex items-center gap-2">
        {!isDone && !isInProgress && onStart && (
          <button
            type="button"
            disabled={busy}
            onClick={() => onStart(task.id)}
            className="inline-flex items-center gap-1 rounded-xl border border-brand-100 bg-primary-soft px-3 py-1.5 text-sm font-medium text-primary-deep transition hover:bg-brand-100 disabled:opacity-60"
          >
            <PlayCircle size={16} />
            开始做
          </button>
        )}
        {!isDone && onComplete && (
          <button
            type="button"
            disabled={busy}
            onClick={() => onComplete(task.id)}
            className="inline-flex items-center gap-1 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:opacity-60"
          >
            <Check size={16} />
            完成
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            disabled={busy}
            onClick={() => onDelete(task.id)}
            className="ml-auto inline-flex items-center gap-1 rounded-xl px-2.5 py-1.5 text-sm text-slate-400 transition hover:bg-rose-50 hover:text-rose-500 disabled:opacity-60"
          >
            <Trash2 size={16} />
          </button>
        )}
      </div>
    </article>
  )
}
