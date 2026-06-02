import { LogOut, ListChecks } from 'lucide-react'
import { Link } from 'react-router-dom'
import { createTask, getDailyReport, parseTask } from '../api'
import DailyReport from '../components/DailyReport'
import ParsePreview from '../components/ParsePreview'
import TaskInput from '../components/TaskInput'
import TaskList from '../components/TaskList'
import TimePickerModal from '../components/TimePickerModal'
import { useAuth } from '../hooks/useAuth'
import { useTasks } from '../hooks/useTasks'
import { useEffect, useState } from 'react'

export default function Home() {
  const { user, signOut } = useAuth()
  const { tasks, loading, error, fetchTasks, completeTask, removeTask } = useTasks({ page_size: 5 })
  const [toast, setToast] = useState('')
  const [parsed, setParsed] = useState(null)
  const [parseOpen, setParseOpen] = useState(false)
  const [timeOpen, setTimeOpen] = useState(false)
  const [timeCallback, setTimeCallback] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [reportState, setReportState] = useState({ report: null, loading: true, error: '' })

  useEffect(() => {
    getDailyReport()
      .then((result) => setReportState({ report: result.report, loading: false, error: '' }))
      .catch(() => setReportState({ report: null, loading: false, error: '日报加载失败' }))
  }, [])

  const showToast = (message) => {
    setToast(message)
    window.setTimeout(() => setToast(''), 2500)
  }

  const handleParse = async (rawInput) => {
    setSubmitting(true)
    try {
      const result = await parseTask(rawInput)
      setParsed(result.parsed)
      setParseOpen(true)
      if (!result.parsed?.is_time_clear) {
        showToast('时间不明确，请补充提醒时间')
      }
    } catch (err) {
      setParsed({ content: rawInput, category: '其他', remind_time: null, is_time_clear: false, parse_error: err.message })
      setParseOpen(true)
      showToast('解析失败，请手动填写')
    } finally {
      setSubmitting(false)
    }
  }

  const handleCreate = async (form) => {
    setSaving(true)
    try {
      await createTask(form)
      setParseOpen(false)
      setParsed(null)
      await fetchTasks()
      showToast('已保存')
    } catch {
      showToast('创建失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  const handlePickTime = (callback) => {
    setTimeCallback(() => callback)
    setTimeOpen(true)
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
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">AI 秘书</h1>
          <p className="mt-1 text-sm text-slate-500">{user?.email}</p>
        </div>
        <button type="button" onClick={signOut} className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600">
          <LogOut size={16} />
          退出
        </button>
      </header>

      {toast && <div className="mt-4 rounded-md bg-slate-900 px-4 py-2 text-sm text-white">{toast}</div>}

      <div className="mt-5">
        <TaskInput onSubmit={handleParse} loading={submitting} />
      </div>

      <div className="mt-5">
        <DailyReport report={reportState.report} loading={reportState.loading} error={reportState.error} />
      </div>

      <section className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-950">最近记录</h2>
          <Link to="/tasks" className="inline-flex items-center gap-1 text-sm text-primary">
            <ListChecks size={16} />
            全部
          </Link>
        </div>
        {error && <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
        <TaskList tasks={tasks} loading={loading} onComplete={handleComplete} onDelete={handleDelete} busyId={busyId} />
      </section>

      <ParsePreview
        open={parseOpen}
        parsed={parsed}
        loading={saving}
        onCancel={() => setParseOpen(false)}
        onConfirm={handleCreate}
        onPickTime={handlePickTime}
      />
      <TimePickerModal
        open={timeOpen}
        onClose={() => setTimeOpen(false)}
        onConfirm={(value) => {
          timeCallback?.(value)
          setTimeOpen(false)
        }}
      />
    </main>
  )
}
