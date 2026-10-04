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

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error?.response?.status === 401) {
      await supabase.auth.signOut()
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }
    return Promise.reject(error)
  },
)

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

export const startTask = (id) =>
  updateTask(id, { status: 'in_progress' })

export const checkinTask = (id, data) =>
  api.post(`/tasks/${id}/checkin`, data).then((response) => response.data)

export const replyTask = (id, data) =>
  api.post(`/tasks/${id}/reply`, data).then((response) => response.data)

export const snoozeTask = (id) =>
  api.post(`/tasks/${id}/snooze`).then((response) => response.data)

export const getBriefing = () =>
  api.get('/secretary/briefing').then((response) => response.data)

export const getSecretaryMessages = (limit = 30) =>
  api.get('/secretary/messages', { params: { limit } }).then((response) => response.data)

export const getSecretaryOpening = () =>
  api.get('/secretary/opening').then((response) => response.data)

export const sendSecretaryChat = (message) =>
  api.post('/secretary/chat', { message }).then((response) => response.data)

export const searchSecretaryMessages = (q) =>
  api.get('/secretary/messages/search', { params: { q } }).then((response) => response.data)

export const getSummaryReport = (period) =>
  api.get('/reports/summary', { params: { period } }).then((response) => response.data)

export const listColleagues = () => api.get('/delegation/colleagues').then(r => r.data)
export const saveColleague = data => api.post('/delegation/colleagues', data).then(r => r.data)
export const editColleague = (id,data) => api.patch(`/delegation/colleagues/${id}`,data).then(r => r.data)
export const listDelegations = () => api.get('/delegation/tasks').then(r => r.data)
export const createDelegation = data => api.post('/delegation/tasks',data).then(r => r.data)
export const parseDelegation = raw_input => api.post('/delegation/parse',{raw_input}).then(r => r.data)
export const actOnDelegation = (id,action,content) => api.post(`/delegation/tasks/${id}/action`,{action,content}).then(r => r.data)
export const delegationEvents = id => api.get(`/delegation/tasks/${id}/events`).then(r => r.data)
export const delegationSettings = () => api.get('/delegation/settings').then(r => r.data)
