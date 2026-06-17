import dayjs from 'dayjs'
import { AlertTriangle, CheckCircle2, Clock, Flag, PlayCircle, Send, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'

function TaskLine({ task, accent = 'slate' }) {
  if (!task) return null
  const dot = {
    slate: 'bg-slate-300',
    indigo: 'bg-primary',
    amber: 'bg-amber-400',
    red: 'bg-rose-500',
  }[accent]
  return (
    <div className="flex items-start gap-2.5 rounded-xl bg-white px-3.5 py-2.5 ring-1 ring-slate-200/80">
      <span className={`mt-1.5 h-2 w-2 flex-none rounded-full ${dot}`} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-900">{task.content}</p>
        <p className="mt-0.5 text-xs text-slate-500">
          优先级 {task.priority_level || task.priority || 'B'}
          {task.related_person ? ` · ${task.related_person}` : ''}
          {task.remind_time ? ` · ${dayjs(task.remind_time).format('M月D日 HH:mm')}` : ' · 未设置时间'}
        </p>
      </div>
    </div>
  )
}

function StatCard({ value, label, alert, onClick }) {
  const Component = onClick ? 'button' : 'div'
  return (
    <Component
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`flex-1 rounded-2xl border px-3.5 py-3 text-left transition ${
        alert
          ? 'border-white bg-white hover:bg-rose-50'
          : 'border-white/20 bg-white/15 backdrop-blur-sm hover:bg-white/25'
      } ${onClick ? 'cursor-pointer focus:outline-none focus:ring-2 focus:ring-white/80' : ''}`}
    >
      <div
        className={`text-2xl font-extrabold leading-none tracking-tight ${
          alert ? 'text-rose-600' : 'text-white'
        }`}
      >
        {value}
      </div>
      <div className={`mt-1.5 text-xs ${alert ? 'font-semibold text-slate-600' : 'text-white/85'}`}>
        {label}
      </div>
    </Component>
  )
}

export default function SecretaryBriefing({
  briefing,
  loading,
  error,
  onComplete,
  onStart,
  onSnooze,
  onCheckin,
  busyId,
}) {
  const [noteById, setNoteById] = useState({})
  const navigate = useNavigate()

  if (loading) {
    return (
      <section className="rounded-xl2 bg-white p-5 text-sm text-slate-500 shadow-soft ring-1 ring-slate-200">
        秘书简报加载中...
      </section>
    )
  }

  if (error) {
    return (
      <section className="rounded-xl2 bg-rose-50 p-5 text-sm text-rose-600 ring-1 ring-rose-100">
        {error}
      </section>
    )
  }

  if (!briefing) {
    return (
      <section className="rounded-xl2 bg-white p-5 text-sm text-slate-500 shadow-soft ring-1 ring-slate-200">
        暂无秘书简报
      </section>
    )
  }

  const stats = briefing.stats || {}
  const waitingOverdue = stats.waiting_overdue || 0
  const blocked = stats.blocked || 0
  const activeToday = (briefing.today || []).filter(
    (task) => !['done', 'cancelled'].includes(task.status),
  )

  return (
    <section className="space-y-3.5">
      {/* Hero greeting */}
      <div className="relative overflow-hidden rounded-xl2 bg-gradient-to-br from-primary via-brand-600 to-violet-700 p-5 text-white shadow-glow">
        <div className="pointer-events-none absolute -right-10 -top-16 h-56 w-56 rounded-full bg-white/15 blur-2xl" />
        <div className="relative">
          <div className="flex items-center gap-2 text-xs text-white/80">
            <Sparkles size={15} />
            秘书简报 · {dayjs().format('M月D日 dddd')}
          </div>
          <p className="mt-2 text-lg font-semibold leading-snug">{briefing.greeting}</p>
          <div className="mt-4 flex gap-2.5">
            <StatCard value={stats.done_today || 0} label="今日已完成" onClick={() => navigate('/tasks?status=done')} />
            <StatCard value={stats.in_progress || 0} label="进行中" onClick={() => navigate('/tasks?status=in_progress')} />
            <StatCard value={stats.overdue || 0} label="逾期待处理" alert onClick={() => navigate('/tasks?view=overdue')} />
          </div>
          {(waitingOverdue > 0 || blocked > 0) && (
            <p className="mt-3 text-xs text-white/85">
              另外：等回复超时 {waitingOverdue} · 受阻 {blocked}，建议优先盯一下
            </p>
          )}
        </div>
      </div>

      {/* Top priority */}
      {briefing.top_priority && (
        <div className="rounded-xl2 border border-brand-100 bg-gradient-to-br from-primary-soft to-violet-50 p-4">
          <div className="mb-2.5 flex items-center gap-2 text-sm font-bold text-primary-deep">
            <Flag size={16} />
            最该先干这件
          </div>
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-primary text-sm font-extrabold text-white shadow-[0_4px_10px_rgba(79,70,229,0.3)]">
              1
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[15px] font-semibold text-slate-900">
                {briefing.top_priority.content}
              </p>
              <p className="mt-0.5 text-xs text-slate-600">
                {briefing.top_priority.category || '工作'}
                {briefing.top_priority.related_person ? ` · ${briefing.top_priority.related_person}` : ''}
                {briefing.top_priority.remind_time
                  ? ` · ${dayjs(briefing.top_priority.remind_time).format('M月D日 HH:mm')}`
                  : ''}
              </p>
            </div>
            <span className="flex-none rounded-lg bg-primary px-2 py-1 text-xs font-bold text-white">
              {briefing.top_priority.priority_level || 'S'} 级
            </span>
          </div>
        </div>
      )}

      {/* Waiting response overdue */}
      {!!briefing.waiting_overdue?.length && (
        <div className="rounded-xl2 border border-amber-200 bg-amber-50/70 p-4">
          <div className="mb-2.5 flex items-center gap-2 text-sm font-bold text-amber-700">
            <Clock size={16} />
            等回复超时，要不要催一下
          </div>
          <div className="space-y-2">
            {briefing.waiting_overdue.slice(0, 3).map((task) => (
              <TaskLine key={task.id} task={task} accent="amber" />
            ))}
          </div>
        </div>
      )}

      {/* Blocked */}
      {!!briefing.blocked?.length && (
        <div className="rounded-xl2 border border-rose-200 bg-rose-50/70 p-4">
          <div className="mb-2.5 flex items-center gap-2 text-sm font-bold text-rose-700">
            <AlertTriangle size={16} />
            卡住了，需要你拍板
          </div>
          <div className="space-y-2">
            {briefing.blocked.slice(0, 3).map((task) => (
              <TaskLine key={task.id} task={task} accent="red" />
            ))}
          </div>
        </div>
      )}

      {/* Overdue gentle reminder */}
      {!!briefing.overdue?.length && (
        <div className="rounded-xl2 border border-rose-200 bg-rose-50/70 p-4">
          <div className="mb-2.5 flex items-center gap-2 text-sm font-bold text-rose-600">
            <AlertTriangle size={16} />
            逾期了，要不要处理一下
          </div>
          <div className="space-y-2.5">
            {briefing.overdue.slice(0, 3).map((task) => (
              <div key={task.id} className="rounded-xl bg-white p-3 ring-1 ring-rose-100">
                <TaskLine task={task} accent="red" />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => onStart(task.id)}
                    className="rounded-lg bg-rose-500 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-rose-600 disabled:opacity-60"
                  >
                    我来处理
                  </button>
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => onSnooze(task.id)}
                    className="rounded-lg bg-white px-3 py-1.5 text-sm text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 disabled:opacity-60"
                  >
                    明天再说
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Check-ins */}
      {!!briefing.checkins?.length && (
        <div className="rounded-xl2 border border-slate-200 bg-white p-4 shadow-soft">
          <div className="mb-2.5 flex items-center gap-2 text-sm font-bold text-slate-700">
            <Send size={16} />
            进度问询
          </div>
          <div className="space-y-2.5">
            {briefing.checkins.slice(0, 2).map((task) => (
              <div key={task.id} className="rounded-xl bg-slate-50 p-3.5 ring-1 ring-slate-100">
                <p className="text-sm font-medium text-slate-900">“{task.content}” 进展咋样了？</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => onComplete(task.id)}
                    className="inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-sm text-white transition hover:bg-primary-deep disabled:opacity-60"
                  >
                    <CheckCircle2 size={15} />
                    已完成
                  </button>
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => onCheckin(task.id, { status: 'in_progress' })}
                    className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-1.5 text-sm text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-50 disabled:opacity-60"
                  >
                    <PlayCircle size={15} />
                    还在做
                  </button>
                </div>
                <div className="mt-3 flex gap-2">
                  <input
                    value={noteById[task.id] || ''}
                    onChange={(event) =>
                      setNoteById((current) => ({ ...current, [task.id]: event.target.value }))
                    }
                    placeholder="遇到卡点，记一句"
                    className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/10"
                  />
                  <button
                    type="button"
                    disabled={busyId === task.id || !noteById[task.id]?.trim()}
                    onClick={() =>
                      onCheckin(task.id, { progress_note: noteById[task.id].trim(), status: 'in_progress' })
                    }
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
                  >
                    记录
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Today */}
      {!!activeToday.length && (
        <div className="rounded-xl2 border border-slate-200 bg-white p-4 shadow-soft">
          <div className="mb-2.5 flex items-center gap-2 text-sm font-bold text-slate-700">
            <Clock size={16} />
            今日待办
          </div>
          <div className="space-y-2">
            {activeToday.slice(0, 5).map((task) => (
              <TaskLine key={task.id} task={task} accent="indigo" />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
