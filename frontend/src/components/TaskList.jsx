import { Sparkles } from 'lucide-react'
import TaskCard from './TaskCard'

export default function TaskList({ tasks, loading, emptyText, onComplete, onStart, onDelete, onReply, busyId }) {
  if (loading) {
    return (
      <div className="rounded-xl2 bg-white p-6 text-center text-slate-500 shadow-soft ring-1 ring-slate-200">
        加载中...
      </div>
    )
  }

  if (!tasks.length) {
    return (
      <div className="rounded-xl2 bg-white p-8 text-center shadow-soft ring-1 ring-slate-200">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
          <Sparkles size={22} />
        </div>
        <p className="text-slate-600">{emptyText || '还没有待办，输入一句话开始吧'}</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {tasks.map((task) => (
        <TaskCard
          key={task.id}
          task={task}
          busy={busyId === task.id}
          onComplete={onComplete}
          onStart={onStart}
          onDelete={onDelete}
          onReply={onReply}
        />
      ))}
    </div>
  )
}
