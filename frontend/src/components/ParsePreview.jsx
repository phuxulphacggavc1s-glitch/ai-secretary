import dayjs from 'dayjs'
import { useEffect, useState } from 'react'

const categories = ['工作', '生活', '灵感', '财务', '学习', '其他']

export default function ParsePreview({ parsed, open, onCancel, onConfirm, onPickTime, loading }) {
  const [form, setForm] = useState({ content: '', category: '其他', remind_time: '', priority: 1 })

  useEffect(() => {
    if (parsed) {
      setForm({
        content: parsed.content || '',
        category: parsed.category || '其他',
        remind_time: parsed.remind_time || '',
        priority: 1,
      })
    }
  }, [parsed])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex items-end bg-slate-950/40 p-4 sm:items-center sm:justify-center">
      <section className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <h2 className="text-lg font-semibold text-slate-950">AI 已解析</h2>
        {parsed?.parse_error && <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-700">解析失败，请手动填写</p>}
        <div className="mt-4 space-y-4">
          <label className="block text-sm font-medium text-slate-700">
            内容
            <input value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2" />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            分类
            <select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2">
              {categories.map((category) => <option key={category}>{category}</option>)}
            </select>
          </label>
          <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-600">
            <div className="font-medium text-slate-700">提醒时间</div>
            <div className="mt-1">{form.remind_time ? dayjs(form.remind_time).format('YYYY-MM-DD HH:mm') : '未识别，点击设置'}</div>
            <button type="button" onClick={() => onPickTime((value) => setForm({ ...form, remind_time: value }))} className="mt-2 text-primary">设置时间</button>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-md px-4 py-2 text-slate-600">取消</button>
          <button
            type="button"
            disabled={loading || !form.content.trim()}
            onClick={() => onConfirm(form)}
            className="rounded-md bg-primary px-4 py-2 text-white disabled:opacity-60"
          >
            {loading ? '保存中...' : '确认保存'}
          </button>
        </div>
      </section>
    </div>
  )
}
