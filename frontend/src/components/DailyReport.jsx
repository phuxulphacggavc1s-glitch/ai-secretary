export default function DailyReport({ report, loading, error }) {
  return (
    <section className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-slate-950">今日总结</h2>
        {report && (
          <div className="text-xs text-slate-500">
            完成 {report.done_count || 0} · 待办 {report.pending_count || 0}
          </div>
        )}
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        {loading ? '加载中...' : error || report?.content || '今日总结将在晚上9点生成'}
      </p>
    </section>
  )
}
