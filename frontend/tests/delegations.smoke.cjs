const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname,'..');
const authKey = 'ai-secretary-session';
const output = process.env.PREVIEW_OUTPUT || path.join(root,'preview-artifacts');
const colleagues = [{id:'c1',name:'张三',wecom_userid:'ZhangSan',aliases:['数据同事'],active:true}];
let tasks = [{
 id:'t1',colleague_id:'c1',colleague:colleagues[0],content:'整理本周销售数据并核对渠道回款，今天下午提交完整表格。',
 approval_code:'1024',approval_status:'pending_approval',delivery_status:'not_sent',task_status:'not_started',
 approval_requested_at:'2026-10-04T01:00:00Z',scheduled_at:'2026-10-04T01:00:00Z',due_at:'2026-10-04T09:00:00Z',
 paused_reason:null,next_followup_at:null,
}];
const errors=[];
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try {
 const context=await browser.newContext();
 await context.addInitScript(({authKey})=>{
   const b64=x=>btoa(JSON.stringify(x));
   const exp=Math.floor(Date.now()/1000)+3600;
   localStorage.setItem(authKey,JSON.stringify({access_token:b64({alg:'HS256',typ:'JWT'})+'.'+b64({sub:'preview-user',exp})+'.signature',refresh_token:'preview-refresh',token_type:'bearer',expires_in:3600,expires_at:exp,user:{id:'preview-user',email:'preview@example.com',aud:'authenticated',role:'authenticated'}}));
 },{authKey});
 await context.route('**/auth/v1/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({id:'preview-user',email:'preview@example.com'})}));
 await context.route('**/delegation/**', async route=>{
   const request=route.request(), pathname=new URL(request.url()).pathname, data=request.postDataJSON();
   let result={};
   if(pathname.endsWith('/settings')) result={enabled:true};
   else if(pathname.endsWith('/colleagues') && request.method()==='GET') result={colleagues};
   else if(pathname.endsWith('/colleagues') && request.method()==='POST'){
     if(data.wecom_userid==='invalid account') return route.fulfill({status:422,contentType:'application/json',
       body:JSON.stringify({detail:[{loc:['body','wecom_userid'],msg:'invalid pattern',type:'string_pattern_mismatch'}]})});
     const colleague={...data,id:'c'+(colleagues.length+1),active:true}; colleagues.push(colleague);result={colleague};
   } else if(pathname.includes('/colleagues/') && request.method()==='PATCH'){
     const id=pathname.split('/').pop();Object.assign(colleagues.find(c=>c.id===id),data);result={colleague:colleagues.find(c=>c.id===id)};
   } else if(pathname.endsWith('/tasks') && request.method()==='GET') result={tasks};
   else if(pathname.endsWith('/tasks') && request.method()==='POST'){
     const task={...data,id:'t'+(tasks.length+1),approval_code:'2048',colleague:colleagues.find(c=>c.id===data.colleague_id),approval_status:'scheduled',delivery_status:'not_sent',task_status:'not_started'};
     tasks.push(task);result={task};
   } else if(pathname.endsWith('/action')){
     const id=pathname.split('/').at(-2),task=tasks.find(t=>t.id===id);
     if(data.action==='approve')Object.assign(task,{approval_status:'approved',delivery_status:'sent',task_status:'awaiting_reply'});
     result={task};
   } else if(pathname.endsWith('/events'))result={events:[{id:'e1',actor_type:'system',event_type:'approval_sent',created_at:'2026-10-04T01:00:00Z',note:'已请求负责人批准'}]};
   else if(pathname.endsWith('/parse'))result={parsed:{colleague_id:'c1',content:'整理库存',scheduled_at:'2026-10-05T01:00:00Z',due_at:null}};
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(result)});
 });
 const page=await context.newPage();
 page.on('pageerror',error=>errors.push(error.message));
 for(const [name,width,height] of [['desktop',1280,900],['mobile',375,812]]){
   await page.setViewportSize({width,height});
   await page.goto('http://127.0.0.1:5175/delegations');
   await page.getByRole('heading',{name:'委派任务',exact:true}).waitFor();
   await page.getByText('整理本周销售数据并核对渠道回款，今天下午提交完整表格。').waitFor();
   await page.screenshot({path:path.join(output,'delegations-'+name+'.png'),fullPage:true});
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
   assert(!overflow,name+' page overflows');
   await page.getByRole('button',{name:'安排任务',exact:true}).click();
   await page.getByRole('dialog').waitFor();
   await page.screenshot({path:path.join(output,'delegation-form-'+name+'.png'),fullPage:true});
   const dialogOverflow=await page.getByRole('dialog').evaluate(el=>el.scrollWidth>el.clientWidth);
   assert(!dialogOverflow,name+' dialog overflows');
   await page.getByRole('button',{name:'关闭',exact:true}).click();
 }
 await page.getByRole('button',{name:'批准下达',exact:true}).click();
 await page.getByText('等待回复',{exact:true}).waitFor();
 assert(tasks[0].delivery_status==='sent');
 await page.getByRole('button',{name:'查看记录',exact:true}).click();
 await page.getByText('已请求负责人批准').waitFor();
 await page.getByRole('button',{name:'关闭',exact:true}).click();
 await page.getByRole('button',{name:'同事目录',exact:true}).click();
 await page.getByRole('button',{name:'添加同事',exact:true}).click();
 await page.getByLabel('姓名',{exact:true}).fill('李四');
 await page.getByLabel('企业微信账号 UserID').fill('invalid account');
 await page.getByRole('button',{name:'保存',exact:true}).click();
 await page.getByRole('alert').filter({hasText:'填写内容无效'}).waitFor();
 await page.getByLabel('企业微信账号 UserID').fill('LiSi');
 await page.getByLabel('别名',{exact:true}).fill('运营，四哥');
 await page.getByRole('button',{name:'保存',exact:true}).click();
 await page.getByText('LiSi',{exact:true}).waitFor();
 await page.getByRole('switch',{name:'启用同事 李四',exact:true}).click();
 await page.locator('input[title="启用同事"]').waitFor();
 assert(!await page.getByRole('switch',{name:'启用同事 李四',exact:true}).isChecked());
 await page.getByRole('button',{name:'任务',exact:true}).click();
 await page.getByRole('button',{name:'安排任务',exact:true}).click();
 await page.getByLabel('接收同事').selectOption('c1');
 await page.getByLabel('任务内容').fill('明天整理渠道库存');
 await page.getByLabel('下达时间（北京时间）').fill('2026-10-05T09:00');
 await page.getByRole('button',{name:'保存',exact:true}).click();
 await page.getByRole('dialog').waitFor({state:'hidden'});
 await page.locator('article').getByText('明天整理渠道库存',{exact:true}).waitFor();
 assert(tasks[1].scheduled_at==='2026-10-05T01:00:00.000Z');
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({result:'passed',viewports:['1280x900','375x812'],flows:['approval','events','colleague create','validation error','colleague disable','task create'],screenshots:output}));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
