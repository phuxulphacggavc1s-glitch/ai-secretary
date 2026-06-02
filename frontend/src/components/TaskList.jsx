import TaskCard from './TaskCard'

export default function TaskList({ tasks, loading, emptyText, onComplete, onDelete, busyId }) {
  if (loading) {
    return <div className="rounded-lg bg-white p-6 text-center text-slate-500 ring-1 ring-slate-200">加载中...</div>
  }

  if (!tasks.length) {
    return (
      <div className="rounded-lg bg-white p-8 text-center ring-1 ring-slate-200">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-primary">AI</div>
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
          onDelete={onDelete}
        />
      ))}
    </div>
  )
}
