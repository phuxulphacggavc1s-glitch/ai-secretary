import dayjs from 'dayjs'
import { Check, Trash2 } from 'lucide-react'

const badgeClass = {
  工作: 'bg-blue-50 text-blue-700',
  财务: 'bg-green-50 text-green-700',
  生活: 'bg-orange-50 text-orange-700',
  灵感: 'bg-purple-50 text-purple-700',
  学习: 'bg-teal-50 text-teal-700',
  其他: 'bg-gray-100 text-gray-700',
}

export default function TaskCard({ task, onComplete, onDelete, busy }) {
  const isDone = task.status === 'done'

  return (
    <article className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${badgeClass[task.category] || badgeClass.其他}`}>
          {task.category || '其他'}
        </span>
        <span className="text-xs text-slate-400">优先级 {task.priority || 1}</span>
        {isDone && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-500">已完成</span>}
      </div>
      <h3 className={`mt-3 text-base font-medium ${isDone ? 'text-slate-400 line-through' : 'text-slate-950'}`}>
        {task.content}
      </h3>
      <p className="mt-2 text-sm text-slate-500">
        {task.remind_time ? dayjs(task.remind_time).format('M月D日 HH:mm') : '未设置提醒时间'}
      </p>
      <div className="mt-4 flex gap-2">
        {!isDone && (
          <button
            type="button"
            disabled={busy}
            onClick={() => onComplete(task.id)}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 disabled:opacity-60"
          >
            <Check size={16} />
            完成
          </button>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={() => onDelete(task.id)}
          className="inline-flex items-center gap-1 rounded-md border border-red-200 px-3 py-1.5 text-sm text-red-600 disabled:opacity-60"
        >
          <Trash2 size={16} />
          删除
        </button>
      </div>
    </article>
  )
}
