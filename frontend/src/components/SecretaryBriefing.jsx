import dayjs from 'dayjs'
import { AlertTriangle, CheckCircle2, Clock, PlayCircle, Send, Sparkles } from 'lucide-react'
import { useState } from 'react'

function TaskLine({ task }) {
  if (!task) return null
  return (
    <div className="rounded-md bg-white px-3 py-2 ring-1 ring-slate-200">
      <p className="text-sm font-medium text-slate-950">{task.content}</p>
      <p className="mt-1 text-xs text-slate-500">
        优先级 {task.priority || 1}
        {task.remind_time ? ` · ${dayjs(task.remind_time).format('M月D日 HH:mm')}` : ' · 未设置时间'}
      </p>
    </div>
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

  if (loading) {
    return <section className="rounded-lg bg-white p-4 text-sm text-slate-500 ring-1 ring-slate-200">秘书简报加载中...</section>
  }

  if (error) {
    return <section className="rounded-lg bg-red-50 p-4 text-sm text-red-600 ring-1 ring-red-100">{error}</section>
  }

  if (!briefing) {
    return <section className="rounded-lg bg-white p-4 text-sm text-slate-500 ring-1 ring-slate-200">暂无秘书简报</section>
  }

  const stats = briefing.stats || {}

  return (
    <section className="space-y-4 rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <div>
        <div className="flex items-center gap-2 text-primary">
          <Sparkles size={18} />
          <h2 className="text-base font-semibold">秘书简报</h2>
        </div>
        <p className="mt-2 text-lg font-semibold text-slate-950">{briefing.greeting}</p>
        <p className="mt-1 text-sm text-slate-500">
          今天完成 {stats.done_today || 0} · 进行中 {stats.in_progress || 0} · 逾期 {stats.overdue || 0}
        </p>
      </div>

      {briefing.top_priority && (
        <div className="rounded-lg bg-indigo-50 p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-indigo-700">
            <Clock size={16} />
            最该先干
          </div>
          <TaskLine task={briefing.top_priority} />
        </div>
      )}

      {!!briefing.overdue?.length && (
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-orange-700">
            <AlertTriangle size={16} />
            逾期温柔提醒
          </div>
          <div className="space-y-2">
            {briefing.overdue.slice(0, 3).map((task) => (
              <div key={task.id} className="rounded-md bg-orange-50 p-3">
                <TaskLine task={task} />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => onStart(task.id)}
                    className="rounded-md bg-white px-3 py-1.5 text-sm text-orange-700 ring-1 ring-orange-200 disabled:opacity-60"
                  >
                    我来处理
                  </button>
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => onSnooze(task.id)}
                    className="rounded-md bg-white px-3 py-1.5 text-sm text-slate-600 ring-1 ring-slate-200 disabled:opacity-60"
                  >
                    明天再说
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!!briefing.checkins?.length && (
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Send size={16} />
            进度问询
          </div>
          <div className="space-y-2">
            {briefing.checkins.slice(0, 2).map((task) => (
              <div key={task.id} className="rounded-md bg-slate-50 p-3">
                <p className="text-sm font-medium text-slate-950">“{task.content}” 进展咋样了？</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => onComplete(task.id)}
                    className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm text-white disabled:opacity-60"
                  >
                    <CheckCircle2 size={15} />
                    已完成
                  </button>
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => onCheckin(task.id, { status: 'in_progress' })}
                    className="inline-flex items-center gap-1 rounded-md bg-white px-3 py-1.5 text-sm text-slate-700 ring-1 ring-slate-200 disabled:opacity-60"
                  >
                    <PlayCircle size={15} />
                    还在做
                  </button>
                </div>
                <div className="mt-3 flex gap-2">
                  <input
                    value={noteById[task.id] || ''}
                    onChange={(event) => setNoteById((current) => ({ ...current, [task.id]: event.target.value }))}
                    placeholder="遇到卡点，记一句"
                    className="min-w-0 flex-1 rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-primary"
                  />
                  <button
                    type="button"
                    disabled={busyId === task.id || !noteById[task.id]?.trim()}
                    onClick={() => onCheckin(task.id, { progress_note: noteById[task.id].trim(), status: 'in_progress' })}
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-60"
                  >
                    记录
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!!briefing.today?.length && (
        <div>
          <div className="mb-2 text-sm font-semibold text-slate-700">今日待办</div>
          <div className="space-y-2">
            {briefing.today.slice(0, 5).map((task) => (
              <TaskLine key={task.id} task={task} />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
