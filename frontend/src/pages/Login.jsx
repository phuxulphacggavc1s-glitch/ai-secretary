import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../supabase'

// 把英文错误翻译成中文
function translateError(msg) {
  if (!msg) return '操作失败，请重试'
  if (msg.includes('Failed to fetch') || msg.includes('fetch'))
    return '网络错误：无法连接服务器。请检查 .env.local 里的 VITE_SUPABASE_URL 和 VITE_SUPABASE_ANON_KEY 是否填写正确，然后重启前端（Ctrl+C → npm run dev）'
  if (msg.includes('Invalid login credentials'))
    return '邮箱或密码错误'
  if (msg.includes('Email not confirmed'))
    return '邮箱未验证，请去 Supabase 控制台 Authentication → Providers → Email，关闭 Confirm email 选项后再试'
  if (msg.includes('User already registered'))
    return '该邮箱已注册，请直接登录'
  if (msg.includes('Password should be at least'))
    return '密码至少需要6位'
  if (msg.includes('Unable to validate email'))
    return '邮箱格式不正确'
  return msg
}

export default function Login() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      if (mode === 'login') {
        const { error: authError } = await supabase.auth.signInWithPassword({ email, password })
        if (authError) throw authError
        navigate('/')
      } else {
        const { data, error: authError } = await supabase.auth.signUp({ email, password })
        if (authError) throw authError
        // 如果开启了邮箱验证，session 会是 null
        if (data.session) {
          navigate('/')
        } else {
          setSuccess('注册成功！请去邮箱点击验证链接后再登录。\n或者去 Supabase 控制台关闭邮箱验证后直接登录。')
        }
      }
    } catch (err) {
      setError(translateError(err.message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-8">
      <section className="w-full max-w-sm rounded-lg bg-white p-6 shadow-sm ring-1 ring-slate-200">
        <h1 className="text-2xl font-semibold text-slate-950">AI 秘书</h1>
        <p className="mt-2 text-sm text-slate-500">一句话记录工作、生活和提醒。</p>
        <div className="mt-6 grid grid-cols-2 rounded-md bg-slate-100 p-1">
          {[
            ['login', '登录'],
            ['signup', '注册'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setMode(value)}
              className={`rounded px-3 py-2 text-sm ${mode === value ? 'bg-white text-primary shadow-sm' : 'text-slate-500'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <form className="mt-6 space-y-4" onSubmit={submit}>
          <label className="block text-sm font-medium text-slate-700">
            邮箱
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 outline-none focus:border-primary"
            />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            密码
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 outline-none focus:border-primary"
            />
          </label>
          {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600 whitespace-pre-line">{error}</p>}
          {success && <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-700 whitespace-pre-line">{success}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-primary px-4 py-2 font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? '处理中...' : mode === 'login' ? '登录' : '注册'}
          </button>
        </form>
      </section>
    </main>
  )
}
