import { Send } from 'lucide-react'
import { useState } from 'react'

export default function TaskInput({ onSubmit, loading }) {
  const [value, setValue] = useState('')
  const [focused, setFocused] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    if (!value.trim()) return
    await onSubmit(value.trim())
    setValue('')
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-xl2 border border-slate-200/80 bg-white p-3.5 shadow-card"
    >
      <div
        className={`rounded-2xl border bg-slate-50/70 transition ${
          focused ? 'border-primary bg-white ring-4 ring-primary/10' : 'border-slate-200'
        }`}
      >
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          rows={3}
          placeholder="说一句话，我帮你拆成待办，例如：明天下午提醒我给客户报价"
          className="w-full resize-none bg-transparent px-4 py-3 text-base text-slate-900 outline-none placeholder:text-slate-400"
        />
      </div>
      <div className="mt-3 flex items-center justify-between">
        <p className="hidden text-xs text-slate-400 sm:block">
          直接说人话就行，时间、分类、优先级我来帮你判断
        </p>
        <button
          type="submit"
          disabled={loading || !value.trim()}
          className="ml-auto inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-medium text-white shadow-[0_6px_14px_rgba(79,70,229,0.30)] transition hover:bg-primary-deep disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none"
        >
          <Send size={17} />
          {loading ? '解析中...' : '发送'}
        </button>
      </div>
    </form>
  )
}
