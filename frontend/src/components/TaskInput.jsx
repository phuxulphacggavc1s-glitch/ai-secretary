import { Send } from 'lucide-react'
import { useState } from 'react'

export default function TaskInput({ onSubmit, loading }) {
  const [value, setValue] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    if (!value.trim()) return
    await onSubmit(value.trim())
    setValue('')
  }

  return (
    <form onSubmit={submit} className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        rows={4}
        placeholder="例如：明天下午提醒我给客户报价"
        className="w-full resize-none rounded-md border border-slate-300 px-3 py-3 text-base outline-none focus:border-primary"
      />
      <div className="mt-3 flex justify-end">
        <button
          type="submit"
          disabled={loading || !value.trim()}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Send size={18} />
          {loading ? '解析中...' : '发送'}
        </button>
      </div>
    </form>
  )
}
