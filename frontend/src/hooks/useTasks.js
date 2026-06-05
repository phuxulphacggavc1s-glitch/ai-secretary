import { useCallback, useEffect, useState } from 'react'
import { deleteTask, listTasks, startTask, updateTask } from '../api'

export function useTasks(params = {}) {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await listTasks(params)
      setTasks(result.tasks || [])
    } catch (err) {
      setError(err?.response?.data?.detail || '网络错误，请重试')
    } finally {
      setLoading(false)
    }
  }, [JSON.stringify(params)])

  useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  const completeTask = async (id) => {
    await updateTask(id, { status: 'done' })
    await fetchTasks()
  }

  const beginTask = async (id) => {
    await startTask(id)
    await fetchTasks()
  }

  const removeTask = async (id) => {
    await deleteTask(id)
    await fetchTasks()
  }

  return { tasks, loading, error, fetchTasks, completeTask, beginTask, removeTask }
}
