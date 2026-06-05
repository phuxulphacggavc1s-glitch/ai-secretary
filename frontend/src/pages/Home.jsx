import { LogOut, ListChecks } from 'lucide-react'
import { Link } from 'react-router-dom'
import { checkinTask, createTask, getBriefing, parseTask, snoozeTask } from '../api'
import ParsePreview from '../components/ParsePreview'
import SecretaryBriefing from '../components/SecretaryBriefing'
import TaskInput from '../components/TaskInput'
import TaskList from '../components/TaskList'
import TimePickerModal from '../components/TimePickerModal'
import { useAuth } from '../hooks/useAuth'
import { useTasks } from '../hooks/useTasks'
import { useCallback, useEffect, useState } from 'react'

export default function Home() {
  const { user, signOut } = useAuth()
  const { tasks, loading, error, fetchTasks, completeTask, beginTask, removeTask } = useTasks({ page_size: 5 })
  const [toast, setToast] = useState('')
  const [parsed, setParsed] = useState(null)
  const [parseOpen, setParseOpen] = useState(false)
  const [timeOpen, setTimeOpen] = useState(false)
  const [timeCallback, setTimeCallback] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [briefingState, setBriefingState] = useState({ briefing: null, loading: true, error: '' })

  const fetchBriefing = useCallback(async () => {
    setBriefingState((current) => ({ ...current, loading: true, error: '' }))
    try {
      const result = await getBriefing()
      setBriefingState({ briefing: result.briefing, loading: false, error: '' })
    } catch {
      setBriefingState({ briefing: null, loading: false, error: '秘书简报加载失败' })
    }
  }, [])

  useEffect(() => {
    fetchBriefing()
  }, [fetchBriefing])

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
        setTimeCallback(() => (value) => {
          setParsed((current) => ({ ...current, remind_time: value, is_time_clear: true }))
        })
        setTimeOpen(true)
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
      await fetchBriefing()
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
      await fetchBriefing()
      showToast('已完成')
    } catch {
      showToast('操作失败，请重试')
    } finally {
      setBusyId('')
    }
  }

  const handleStart = async (id) => {
    setBusyId(id)
    try {
      await beginTask(id)
      await fetchBriefing()
      showToast('已标记为进行中')
    } catch {
      showToast('操作失败，请重试')
    } finally {
      setBusyId('')
    }
  }

  const handleSnooze = async (id) => {
    setBusyId(id)
    try {
      await snoozeTask(id)
      await fetchBriefing()
      showToast('明天再提醒你')
    } catch {
      showToast('操作失败，请重试')
    } finally {
      setBusyId('')
    }
  }

  const handleCheckin = async (id, body) => {
    setBusyId(id)
    try {
      await checkinTask(id, body)
      await fetchTasks()
      await fetchBriefing()
      showToast('已记录进度')
    } catch {
      showToast('记录失败，请重试')
    } finally {
      setBusyId('')
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('确定删除这条待办吗？')) return
    setBusyId(id)
    try {
      await removeTask(id)
      await fetchBriefing()
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
        <div className="flex items-center gap-2">
          <Link
            to="/tasks"
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600"
          >
            <ListChecks size={16} />
            全部任务
          </Link>
          <button
            type="button"
            onClick={signOut}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600"
          >
            <LogOut size={16} />
            退出
          </button>
        </div>
      </header>

      {toast && <div className="mt-4 rounded-md bg-slate-900 px-4 py-2 text-sm text-white">{toast}</div>}

      <div className="mt-5">
        <TaskInput onSubmit={handleParse} loading={submitting} />
      </div>

      <div className="mt-5">
        <SecretaryBriefing
          briefing={briefingState.briefing}
          loading={briefingState.loading}
          error={briefingState.error}
          onComplete={handleComplete}
          onStart={handleStart}
          onSnooze={handleSnooze}
          onCheckin={handleCheckin}
          busyId={busyId}
        />
      </div>

      <div className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-950">最近任务</h2>
          <Link to="/tasks" className="text-sm text-primary">
            查看全部
          </Link>
        </div>
        <TaskList
          tasks={tasks}
          loading={loading}
          onComplete={handleComplete}
          onStart={handleStart}
          onDelete={handleDelete}
          busyId={busyId}
        />
      </div>

      {parseOpen && parsed && (
        <ParsePreview
          parsed={parsed}
          saving={saving}
          onConfirm={handleCreate}
          onClose={() => {
            setParseOpen(false)
            setParsed(null)
          }}
          onPickTime={handlePickTime}
        />
      )}

      {timeOpen && (
        <TimePickerModal
          onConfirm={(value) => {
            timeCallback?.(value)
            setTimeOpen(false)
          }}
          onClose={() => setTimeOpen(false)}
        />
      )}
    </main>
  )
}
