import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
  {
    auth: {
      persistSession: true,      // 登录状态保存到本地，关浏览器不会掉线
      autoRefreshToken: true,    // 自动刷新 token，不需要重新登录
      storageKey: 'ai-secretary-session', // 本地存储的 key 名
    },
  }
)
