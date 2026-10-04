import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Check, ClipboardList, Clock, History, Loader2, Pencil, Plus, RefreshCw, RotateCcw, Save, Users, X } from 'lucide-react'
import SecretaryAvatar from '../components/SecretaryAvatar'
import { listColleagues, saveColleague, editColleague, listDelegations, createDelegation, parseDelegation, actOnDelegation, delegationEvents, delegationSettings } from '../api'

const field = 'w-full min-w-0 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500'
const command = 'inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm hover:bg-gray-50 disabled:opacity-50'
const primary = 'inline-flex min-h-9 items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-700 disabled:opacity-50'
const statuses = { scheduled:'待到点', pending_approval:'待批准', approved:'已批准', cancelled:'已取消', expired:'已过期', not_started:'待下达', awaiting_reply:'等待回复', acknowledged:'已接收', in_progress:'进行中', completed:'已完成', delayed:'已延期', unresponsive:'跟踪已暂停', sending:'发送中', sent:'已下达', failed:'发送失败', uncertain:'送达待确认' }
const fmt = value => value ? new Intl.DateTimeFormat('zh-CN', { timeZone:'Asia/Shanghai', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false }).format(new Date(value)) : '未设置'
const inputTime = value => value ? new Date(new Date(value).getTime() + 8 * 3600000).toISOString().slice(0,16) : ''
const iso = value => value ? new Date(value + ':00+08:00').toISOString() : null
const errorMessage = err => {
  const detail = err.response?.data?.detail
  return typeof detail === 'string' ? detail : err.response ? '填写内容无效，请检查姓名、账号和时间' : '网络错误，请重试'
}
function status(task) {
  if (['failed','uncertain'].includes(task.delivery_status)) return task.delivery_status
  if (['cancelled','expired','scheduled','pending_approval'].includes(task.approval_status)) return task.approval_status
  return task.task_status
}
function IconButton({ title, busy, children, ...props }) {
  return <button type="button" title={title} aria-label={title} className={command + ' h-9 w-9 px-0'} disabled={busy} {...props}>{busy ? <Loader2 size={16} className="animate-spin" /> : children}</button>
}
function Modal({ title, children, onClose, busy }) {
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-3" role="presentation">
    <section role="dialog" aria-modal="true" aria-label={title} className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-5 shadow-xl">
      <div className="mb-5 flex items-center justify-between gap-3"><h2 className="text-lg font-semibold">{title}</h2><IconButton title="关闭" busy={busy} onClick={onClose}><X size={18} /></IconButton></div>
      {children}
    </section>
  </div>
}
export default function Delegations() {
  const [view,setView] = useState('tasks')
  const [filter,setFilter] = useState('all')
  const [tasks,setTasks] = useState([])
  const [colleagues,setColleagues] = useState([])
  const [enabled,setEnabled] = useState(false)
  const [loading,setLoading] = useState(true)
  const [error,setError] = useState('')
  const [busy,setBusy] = useState('')
  const [modal,setModal] = useState(null)
  const [form,setForm] = useState({})
  const [mode,setMode] = useState('manual')
  const [raw,setRaw] = useState('')
  const [events,setEvents] = useState([])

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [t,c,s] = await Promise.all([listDelegations(),listColleagues(),delegationSettings()])
      setTasks(t.tasks || []); setColleagues(c.colleagues || []); setEnabled(s.enabled); setError('')
    } catch (err) { setError(errorMessage(err)) }
    finally { setLoading(false) }
  },[])
  useEffect(() => { refresh() },[refresh])
  const change = (key,value) => setForm(current => ({...current,[key]:value}))
  const open = (kind,record=null) => {
    setError(''); setModal({kind,record}); setRaw(''); setMode('manual')
    setForm(kind === 'colleague' ? {name:record?.name || '',wecom_userid:record?.wecom_userid || '',aliases:(record?.aliases || []).join('，')} : {colleague_id:'',content:record?.content || '',scheduled_at:'',due_at:''})
  }
  const execute = async (key,operation,close=true) => {
    setBusy(key); setError('')
    try { await operation(); if(close) setModal(null); await refresh() }
    catch(err) { setError(errorMessage(err)) }
    finally { setBusy('') }
  }
  const save = async event => {
    event.preventDefault()
    if(modal.kind === 'colleague') {
      const data={name:form.name,aliases:form.aliases.split(/[,，]/).map(x=>x.trim()).filter(Boolean)}
      await execute('save',()=>modal.record ? editColleague(modal.record.id,data) : saveColleague({...data,wecom_userid:form.wecom_userid}))
    } else if(modal.kind === 'modify') {
      await execute('save',()=>actOnDelegation(modal.record.id,'modify',form.content))
    } else {
      await execute('save',()=>createDelegation({colleague_id:form.colleague_id,content:form.content,scheduled_at:iso(form.scheduled_at),due_at:iso(form.due_at)}))
    }
  }
  const parse = async () => {
    setBusy('parse'); setError('')
    try {
      const {parsed}=await parseDelegation(raw)
      setForm({...parsed,scheduled_at:inputTime(parsed.scheduled_at),due_at:inputTime(parsed.due_at)}); setMode('manual')
    } catch(err) { setError(errorMessage(err)) }
    finally { setBusy('') }
  }
  const history = async task => {
    setBusy(task.id); setError('')
    try { const result=await delegationEvents(task.id); setEvents(result.events || []); setModal({kind:'history',record:task}) }
    catch(err) { setError(errorMessage(err)) }
    finally { setBusy('') }
  }
  const visible = tasks.filter(task => {
    const state=status(task)
    return filter==='all' || (filter==='approval' && ['scheduled','pending_approval'].includes(state)) ||
      (filter==='tracking' && ['awaiting_reply','acknowledged','in_progress','delayed','sending'].includes(state)) ||
      (filter==='completed' && state==='completed') || (filter==='exception' && (task.paused_reason || ['failed','uncertain','unresponsive','expired'].includes(state)))
  })
  return <main className="mx-auto min-h-screen max-w-4xl px-4 py-5 text-gray-900">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 pb-4">
      <div className="flex items-center gap-3"><Link to="/" title="返回秘书" aria-label="返回秘书" className={command + ' h-9 w-9 px-0'}><ArrowLeft size={18}/></Link><SecretaryAvatar size={36}/><h1 className="text-xl font-semibold">委派任务</h1></div>
      <IconButton title="刷新" busy={loading || !!busy} onClick={refresh}><RefreshCw size={17}/></IconButton>
    </header>
    <nav className="mt-5 flex gap-6 border-b border-gray-200" aria-label="委派导航">
      {[['tasks','任务',ClipboardList],['colleagues','同事目录',Users]].map(([key,label,Icon])=><button key={key} onClick={()=>setView(key)} className={'flex min-h-11 items-center gap-2 border-b-2 px-1 text-sm '+(view===key?'border-indigo-600 font-medium text-indigo-700':'border-transparent text-gray-600')}><Icon size={17}/>{label}</button>)}
    </nav>
    {!enabled && <p className="mt-4 border-l-4 border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="status">委派发送尚未启用</p>}
    {error && !modal && <p role="alert" className="mt-4 break-words rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    <div className="my-5 flex flex-wrap items-center justify-between gap-3">
      {view==='tasks' ? <div className="flex max-w-full gap-1 overflow-x-auto" role="tablist" aria-label="任务状态">
        {[['all','全部'],['approval','待批准'],['tracking','跟踪中'],['completed','已完成'],['exception','异常']].map(([key,label])=><button role="tab" aria-selected={filter===key} key={key} onClick={()=>setFilter(key)} className={'min-h-9 shrink-0 rounded-lg px-3 text-sm '+(filter===key?'bg-indigo-100 text-indigo-800':'text-gray-600 hover:bg-gray-100')}>{label}</button>)}
      </div> : <h2 className="text-base font-medium">同事 {colleagues.length} 位</h2>}
      <button className={primary} onClick={()=>open(view==='tasks'?'task':'colleague')} disabled={!!busy}><Plus size={16}/>{view==='tasks'?'安排任务':'添加同事'}</button>
    </div>
    {loading ? <div role="status" className="flex items-center gap-2 py-12 text-gray-500"><Loader2 className="animate-spin" size={18}/>加载中</div> :
      view==='tasks' ? <div className="border-t border-gray-200">
        {visible.length===0 && <p className="py-14 text-center text-sm text-gray-500">暂无委派任务</p>}
        {[...visible].reverse().map(task=><article key={task.id} className="border-b border-gray-200 py-4">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2"><span className="text-sm font-medium">{task.colleague?.name || '同事'}</span><span className="text-xs text-gray-400">#{task.approval_code}</span><span className={'rounded px-2 py-0.5 text-xs '+(['failed','uncertain','unresponsive'].includes(status(task))?'bg-amber-100 text-amber-900':status(task)==='completed'?'bg-emerald-100 text-emerald-800':'bg-gray-100 text-gray-700')}>{statuses[status(task)]}</span></div>
          <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{task.content}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-gray-500"><span className="inline-flex items-center gap-1"><Clock size={13}/>下达 {fmt(task.scheduled_at)}</span><span>截止 {fmt(task.due_at)}</span>{task.next_followup_at && <span>下次跟进 {fmt(task.next_followup_at)}</span>}</div>
          {task.paused_reason && <p className="mt-2 break-words text-xs text-amber-800">{task.paused_reason}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {task.approval_status==='pending_approval' && <button className={primary} disabled={!enabled || !!busy || !task.approval_requested_at} onClick={()=>execute(task.id,()=>actOnDelegation(task.id,'approve'),false)}>{busy===task.id?<Loader2 size={15} className="animate-spin"/>:<Check size={15}/>}批准下达</button>}
            {['scheduled','pending_approval'].includes(task.approval_status) && <><IconButton title="修改任务" busy={!!busy} onClick={()=>open('modify',task)}><Pencil size={16}/></IconButton><IconButton title="取消下达" busy={!!busy} onClick={()=>{if(window.confirm('取消这次下达？')) execute(task.id,()=>actOnDelegation(task.id,'cancel'),false)}}><X size={16}/></IconButton></>}
            {task.delivery_status==='sent' && <IconButton title={task.task_status==='completed'?'重新打开':'标记完成'} busy={!!busy} onClick={()=>execute(task.id,()=>actOnDelegation(task.id,task.task_status==='completed'?'reopen':'complete'),false)}>{task.task_status==='completed'?<RotateCcw size={16}/>:<Check size={16}/>}</IconButton>}
            <IconButton title="查看记录" busy={!!busy} onClick={()=>history(task)}><History size={16}/></IconButton>
          </div>
        </article>)}
      </div> : <div className="border-t border-gray-200">
        {colleagues.length===0 && <p className="py-14 text-center text-sm text-gray-500">暂无同事</p>}
        {colleagues.map(c=><div key={c.id} className="flex items-center justify-between gap-4 border-b border-gray-200 py-4">
          <div className="min-w-0"><p className="break-words text-sm font-medium">{c.name}<span className="ml-2 text-xs font-normal text-gray-500">{c.active?'已启用':'已停用'}</span></p><p className="mt-1 break-all text-xs text-gray-500">{c.wecom_userid}</p>{c.aliases?.length>0 && <p className="mt-1 break-words text-xs text-gray-500">{c.aliases.join('、')}</p>}</div>
          <div className="flex shrink-0 items-center gap-3"><IconButton title="编辑同事" busy={!!busy} onClick={()=>open('colleague',c)}><Pencil size={16}/></IconButton><input type="checkbox" role="switch" aria-label={'启用同事 '+c.name} title={c.active?'停用同事':'启用同事'} className="h-4 w-4 accent-indigo-600" checked={c.active} disabled={!!busy} onChange={()=>execute(c.id,()=>editColleague(c.id,{active:!c.active}),false)}/></div>
        </div>)}
      </div>}
    {modal && <Modal title={{colleague:modal.record?'编辑同事':'添加同事',task:'安排任务',modify:'修改待批准任务',history:'任务记录'}[modal.kind]} onClose={()=>setModal(null)} busy={!!busy}>
      {error && <p role="alert" className="mb-4 break-words rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {modal.kind==='history' ? <ol className="space-y-4">{events.length===0 && <li className="text-sm text-gray-500">暂无记录</li>}{events.map(e=><li key={e.id} className="border-l-2 border-gray-200 pl-3"><p className="text-xs text-gray-500">{fmt(e.created_at)} · {{owner:'负责人',colleague:'同事',system:'秘书'}[e.actor_type]}</p><p className="mt-1 whitespace-pre-wrap break-words text-sm">{e.note || ({created:'已安排',approved:'已批准',cancelled:'已取消',expired:'已过期',approval_sent:'已请求批准',approval_reminder_sent:'已提醒批准',dispatch_sent:'已下达',followup_sent:'已跟进',complete:'标记完成',reopen:'重新打开'}[e.event_type] || '状态已更新')}</p></li>)}</ol> : <form onSubmit={save} className="space-y-4">
        {modal.kind==='colleague' ? <>
          <label className="block space-y-1.5 text-sm"><span>姓名</span><input className={field} required maxLength={100} value={form.name} onChange={e=>change('name',e.target.value)}/></label>
          <label className="block space-y-1.5 text-sm"><span>企业微信账号 UserID</span><input className={field} required maxLength={100} disabled={!!modal.record} value={form.wecom_userid} onChange={e=>change('wecom_userid',e.target.value)}/></label>
          <label className="block space-y-1.5 text-sm"><span>别名</span><input className={field} value={form.aliases} onChange={e=>change('aliases',e.target.value)}/></label>
        </> : <>
          {modal.kind==='task' && <div className="flex gap-2">{[['manual','填写任务'],['natural','一句话安排']].map(([key,label])=><button type="button" key={key} className={mode===key?primary:command} onClick={()=>setMode(key)}>{label}</button>)}</div>}
          {mode==='natural' ? <>
            <label className="block space-y-1.5 text-sm"><span>任务安排</span><textarea className={field} rows={4} maxLength={1000} value={raw} onChange={e=>setRaw(e.target.value)}/></label>
            <button type="button" className={primary} disabled={!raw.trim() || !!busy} onClick={parse}>{busy==='parse'?<Loader2 size={16} className="animate-spin"/>:<ClipboardList size={16}/>}解析</button>
          </> : <>
            {modal.kind==='task' && <label className="block space-y-1.5 text-sm"><span>接收同事</span><select required className={field} value={form.colleague_id} onChange={e=>change('colleague_id',e.target.value)}><option value="">选择同事</option>{colleagues.filter(c=>c.active).map(c=><option key={c.id} value={c.id}>{c.name} · {c.wecom_userid}</option>)}</select></label>}
            <label className="block space-y-1.5 text-sm"><span>任务内容</span><textarea required rows={4} maxLength={1000} className={field} value={form.content} onChange={e=>change('content',e.target.value)}/></label>
            {modal.kind==='task' && <div className="grid gap-4 sm:grid-cols-2"><label className="block min-w-0 space-y-1.5 text-sm"><span>下达时间（北京时间）</span><input type="datetime-local" required className={field} value={form.scheduled_at} onChange={e=>change('scheduled_at',e.target.value)}/></label><label className="block min-w-0 space-y-1.5 text-sm"><span>截止时间（可选）</span><input type="datetime-local" className={field} value={form.due_at} onChange={e=>change('due_at',e.target.value)}/></label></div>}
          </>}
        </>}
        {(modal.kind==='colleague' || mode==='manual') && <div className="flex justify-end border-t border-gray-100 pt-4"><button type="submit" className={primary} disabled={!!busy}>{busy==='save'?<Loader2 size={16} className="animate-spin"/>:<Save size={16}/>}保存</button></div>}
      </form>}
    </Modal>}
  </main>
}
