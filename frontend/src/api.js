import axios from 'axios'
import { supabase } from './supabase'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
})

api.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession()
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`
  }
  return config
})

export const parseTask = (rawInput) =>
  api.post('/tasks/parse', { raw_input: rawInput }).then((response) => response.data)

export const createTask = (taskData) =>
  api.post('/tasks', taskData).then((response) => response.data)

export const listTasks = (params) =>
  api.get('/tasks', { params }).then((response) => response.data)

export const updateTask = (id, data) =>
  api.patch(`/tasks/${id}`, data).then((response) => response.data)

export const deleteTask = (id) =>
  api.delete(`/tasks/${id}`).then((response) => response.data)

export const getDailyReport = (date) =>
  api.get('/reports/daily', { params: { report_date: date } }).then((response) => response.data)

export default api
