import { ArrowLeft, BarChart3, Lightbulb, RefreshCcw, TrendingUp } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getSummaryReport } from '../api'
import { useEffect, useState } from 'react'

const periodOptions = [
  { value: 'week', label: '周汇报' },
  { value: 'month', label: '月总结' },
]

function Stat({ label, value, tone = 'slate' }) {
  const toneClass = {
    slate: 'bg-white text-slate-900 ring-slate-200',
    green: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
    red: 'bg-rose-50 text-rose-700 ring-rose-100',
    indigo: 'bg-indigo-50 text-primary ring-indigo-100',
  }[tone]

  return (
    <div className={`rounded-lg p-3 ring-1 ${toneClass}`}>
      <div className="text-2xl font-extrabold leading-none">{value}</div>
      <div className="mt-1 text-xs font-medium opacity-75">{label}</div>
    </div>
  )
}

function ListBlock({ title, items, emptyText }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-soft">
      <h2 className="text-sm font-bold text-slate-900">{title}</h2>
      {items?.length ? (
        <div className="mt-3 space-y-2">
          {items.map((item) => (
            <div key={item} className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
              {item}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">{emptyText}</p>
      )}
    </section>
  )
}

export default function Reports() {
  const [period, setPeriod] = useState('week')
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchReport = async (targetPeriod = period) => {
    setLoading(true)
    setError('')
    try {
      const result = await getSummaryReport(targetPeriod)
      setReport(result.report)
    } catch {
      setError('复盘生成失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchReport(period)
  }, [period])

  const stats = report?.stats || {}

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 py-5">
      <header className="flex items-center gap-3">
        <Link to="/" className="rounded-md border border-slate-300 bg-white p-2 text-slate-600">
          <ArrowLeft size={18} />
        </Link>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold text-slate-950">复盘总结</h1>
          <p className="mt-1 text-sm text-slate-500">查看周汇报、月总结和改进建议</p>
        </div>
        <button
          type="button"
          onClick={() => fetchReport(period)}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white transition hover:bg-primary-deep disabled:opacity-60"
        >
          <RefreshCcw size={15} className={loading ? 'animate-spin' : ''} />
          生成
        </button>
      </header>

      <div className="mt-5 grid grid-cols-2 gap-2 rounded-xl bg-white p-1 ring-1 ring-slate-200">
        {periodOptions.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setPeriod(item.value)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              period === item.value ? 'bg-primary text-white' : 'text-slate-600 hover:bg-slate-50'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error && <div className="mt-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div>}

      {loading ? (
        <section className="mt-5 rounded-xl bg-white p-5 text-sm text-slate-500 shadow-soft ring-1 ring-slate-200">
          正在生成复盘...
        </section>
      ) : report ? (
        <div className="mt-5 space-y-4">
          <section className="rounded-xl2 bg-gradient-to-br from-primary via-brand-600 to-violet-700 p-5 text-white shadow-glow">
            <div className="flex items-center gap-2 text-xs text-white/80">
              <BarChart3 size={15} />
              {report.period_label} · {report.start_date} 至 {report.end_date}
            </div>
            <p className="mt-3 text-base font-semibold leading-7">{report.summary}</p>
          </section>

          <section className="grid grid-cols-3 gap-2">
            <Stat label="总任务" value={stats.total || 0} tone="indigo" />
            <Stat label="已完成" value={stats.done || 0} tone="green" />
            <Stat label="逾期" value={stats.overdue || 0} tone="red" />
            <Stat label="进行中" value={stats.in_progress || 0} />
            <Stat label="等回复" value={stats.waiting_response || 0} />
            <Stat label="受阻" value={stats.blocked || 0} />
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-soft">
            <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
              <TrendingUp size={16} />
              分类分布
            </div>
            <div className="mt-3 space-y-2">
              {report.category_stats?.length ? report.category_stats.map((item) => (
                <div key={item.category} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
                  <span className="text-slate-700">{item.category}</span>
                  <span className="font-semibold text-slate-900">{item.count}</span>
                </div>
              )) : <p className="text-sm text-slate-500">暂无分类数据</p>}
            </div>
          </section>

          <ListBlock title="本期完成" items={report.highlights} emptyText="本期还没有完成事项" />
          <ListBlock title="需要关注" items={report.risks} emptyText="本期暂无明显风险事项" />

          <section className="rounded-xl border border-amber-200 bg-amber-50 p-4">
            <div className="flex items-center gap-2 text-sm font-bold text-amber-800">
              <Lightbulb size={16} />
              改进建议
            </div>
            <div className="mt-3 space-y-2">
              {report.suggestions?.map((item, index) => (
                <div key={item} className="rounded-lg bg-white px-3 py-2 text-sm leading-6 text-slate-700 ring-1 ring-amber-100">
                  {index + 1}. {item}
                </div>
              ))}
            </div>
          </section>
        </div>
      ) : (
        <section className="mt-5 rounded-xl bg-white p-5 text-sm text-slate-500 shadow-soft ring-1 ring-slate-200">
          暂无复盘数据
        </section>
      )}
    </main>
  )
}
