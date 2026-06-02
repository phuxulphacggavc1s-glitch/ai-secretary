import dayjs from 'dayjs'
import { useState } from 'react'

function shortcutDate(type) {
  const now = dayjs()
  if (type === 'tomorrowMorning') return now.add(1, 'day').hour(9).minute(0)
  if (type === 'tomorrowAfternoon') return now.add(1, 'day').hour(15).minute(0)
  if (type === 'afterTomorrow') return now.add(2, 'day').hour(9).minute(0)
  return now.endOf('month').hour(9).minute(0)
}

export default function TimePickerModal({ open, onClose, onConfirm }) {
  const [date, setDate] = useState(dayjs().add(1, 'day').format('YYYY-MM-DD'))
  const [time, setTime] = useState('09:00')

  if (!open) return null

  const applyShortcut = (type) => {
    const value = shortcutDate(type)
    setDate(value.format('YYYY-MM-DD'))
    setTime(value.format('HH:mm'))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-slate-950/40 p-4 sm:items-center sm:justify-center">
      <section className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <h2 className="text-lg font-semibold text-slate-950">设置提醒时间</h2>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <input type="date" value={date} onChange={(event) => setDate(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2" />
          <input type="time" value={time} onChange={(event) => setTime(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2" />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
          <button type="button" onClick={() => applyShortcut('tomorrowMorning')} className="rounded-md bg-slate-100 px-3 py-2">明天上午9点</button>
          <button type="button" onClick={() => applyShortcut('tomorrowAfternoon')} className="rounded-md bg-slate-100 px-3 py-2">明天下午3点</button>
          <button type="button" onClick={() => applyShortcut('afterTomorrow')} className="rounded-md bg-slate-100 px-3 py-2">后天上午9点</button>
          <button type="button" onClick={() => applyShortcut('monthEnd')} className="rounded-md bg-slate-100 px-3 py-2">月底</button>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md px-4 py-2 text-slate-600">跳过</button>
          <button type="button" onClick={() => onConfirm(dayjs(`${date} ${time}`).toISOString())} className="rounded-md bg-primary px-4 py-2 text-white">确认</button>
        </div>
      </section>
    </div>
  )
}
