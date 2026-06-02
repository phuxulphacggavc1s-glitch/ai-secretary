import { ArrowLeft, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import TaskList from '../components/TaskList'
import { useTasks } from '../hooks/useTasks'
import { useMemo, useState } from 'react'

const tabs = ['全部', '工作', '生活', '灵感', '财务', '学习', '已完成']

export default function Tasks() {
  const [tab, setTab] = useState('全部')
  const [keyword, setKeyword] = useState('')
  const params = tab === '已完成'
    ? { status: 'done', page_size: 50 }
    : { category: tab, page_size: 50 }
  const { tasks, loading, error, completeTask, removeTask } = useTasks(params)
  const [busyId, setBusyId] = useState('')
  const [toast, setToast] = useState('')

  const filtered = useMemo(() => {
    return tasks.filter((task) => task.content?.includes(keyword.trim()))
  }, [tasks, keyword])

  const showToast = (message) => {
    setToast(message)
    window.setTimeout(() => setToast(''), 2500)
  }

  const handleComplete = async (id) => {
    setBusyId(id)
    try {
      await completeTask(id)
      showToast('已完成')
    } catch {
      showToast('操作失败，请重试')
    } finally {
      setBusyId('')
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('确定删除这条待办吗？')) return
    setBusyId(id)
    try {
      await removeTask(id)
      showToast('已删除')
    } catch {
      showToast('删除失败，请重试')
    } finally {
      setBusyId('')
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 py-5">
      <header className="flex items-center gap-3">
        <Link to="/" className="rounded-md border border-slate-300 p-2 text-slate-600">
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="text-xl font-semibold text-slate-950">待办列表</h1>
          <p className="mt-1 text-sm text-slate-500">按分类查看、搜索和处理事项</p>
        </div>
      </header>

      {toast && <div className="mt-4 rounded-md bg-slate-900 px-4 py-2 text-sm text-white">{toast}</div>}

      <div className="mt-5 flex items-center gap-2 rounded-md bg-white px-3 py-2 ring-1 ring-slate-200">
        <Search size={18} className="text-slate-400" />
        <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索待办" className="w-full border-0 bg-transparent outline-none" />
      </div>

      <div className="mt-4 flex gap-2 overflow-x-auto pb-2">
        {tabs.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm ${tab === item ? 'bg-primary text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200'}`}
          >
            {item}
          </button>
        ))}
      </div>

      {error && <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

      <section className="mt-4">
        <TaskList
          tasks={filtered}
          loading={loading}
          emptyText={keyword ? '没有匹配的待办' : '还没有待办，输入一句话开始吧'}
          onComplete={handleComplete}
          onDelete={handleDelete}
          busyId={busyId}
        />
      </section>
    </main>
  )
}
