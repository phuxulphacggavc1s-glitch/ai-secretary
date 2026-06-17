import { ArrowLeft, Search } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { replyTask } from '../api'
import TaskList from '../components/TaskList'
import { useTasks } from '../hooks/useTasks'
import { useMemo, useState } from 'react'

const tabs = ['全部', '工作', '生活', '灵感', '财务', '学习', '待处理', '进行中', '等回复', '受阻', '已完成', '已取消']
const statusByTab = {
  待处理: 'pending',
  进行中: 'in_progress',
  等回复: 'waiting_response',
  受阻: 'blocked',
  已完成: 'done',
  已取消: 'cancelled',
}

export default function Tasks() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialStatus = searchParams.get('status')
  const initialView = searchParams.get('view')
  const initialTab = initialView === 'overdue'
    ? '逾期'
    : Object.entries(statusByTab).find(([, status]) => status === initialStatus)?.[0] || '全部'
  const [tab, setTab] = useState(initialTab)
  const [keyword, setKeyword] = useState('')
  const params = tab === '逾期'
    ? { page_size: 50 }
    : statusByTab[tab]
    ? { status: statusByTab[tab], page_size: 50 }
    : tab === '全部'
      ? { page_size: 50 }
      : { category: tab, page_size: 50 }
  const { tasks, loading, error, fetchTasks, completeTask, beginTask, removeTask } = useTasks(params)
  const [busyId, setBusyId] = useState('')
  const [toast, setToast] = useState('')

  const filtered = useMemo(() => {
    const now = Date.now()
    return tasks.filter((task) => {
      const matchesKeyword = task.content?.includes(keyword.trim())
      if (!matchesKeyword) return false
      if (tab !== '逾期') return true
      if (['done', 'cancelled'].includes(task.status)) return false
      if (!task.remind_time || new Date(task.remind_time).getTime() >= now) return false
      return !task.next_follow_time || new Date(task.next_follow_time).getTime() <= now
    })
  }, [tasks, keyword, tab])

  const handleTabChange = (item) => {
    setTab(item)
    const next = new URLSearchParams()
    if (item === '逾期') {
      next.set('view', 'overdue')
    } else if (statusByTab[item]) {
      next.set('status', statusByTab[item])
    }
    setSearchParams(next, { replace: true })
  }

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

  const handleStart = async (id) => {
    setBusyId(id)
    try {
      await beginTask(id)
      showToast('已标记为进行中')
    } catch {
      showToast('操作失败，请重试')
    } finally {
      setBusyId('')
    }
  }

  const handleReply = async (id, replyText) => {
    setBusyId(id)
    try {
      const result = await replyTask(id, { reply_text: replyText })
      await fetchTasks()
      showToast(`AI 已判断为：${result.judged?.new_status || '已更新'}`)
    } catch {
      showToast('进展判断失败，请重试')
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
        <input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜索待办"
          className="w-full border-0 bg-transparent outline-none"
        />
      </div>

      <div className="mt-4 flex gap-2 overflow-x-auto pb-2">
        {['逾期', ...tabs].map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => handleTabChange(item)}
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
          emptyText="没有找到相关任务"
          onComplete={handleComplete}
          onStart={handleStart}
          onDelete={handleDelete}
          onReply={handleReply}
          busyId={busyId}
        />
      </section>
    </main>
  )
}
