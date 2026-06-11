# AI 秘书国内部署手册（阿里云 ECS）

目标：用你已经备案通过的域名，把 AI 秘书部署到国内 ECS，让朋友可以直接访问。

当前建议架构：

- 域名：`mede-in-ai.com`、`www.mede-in-ai.com`
- ECS：`123.57.180.79`，Ubuntu 22.04
- 前端：React/Vite 构建后由 Nginx 提供静态文件
- 后端：FastAPI 运行在 ECS 本机 `127.0.0.1:8000`
- 对外访问：`https://mede-in-ai.com`，接口走同域 `/api`
- 数据库/Auth：Supabase 暂时保持不动

你截图里显示 ICP 备案已在 2026-06-11 通过，备案号是 `冀ICP备2026020767号`。下一步要做的是 DNS 解析、服务器部署、HTTPS 证书和线上验证。

## 一、上线前确认

本地确认这些文件不要提交到 GitHub：

```powershell
git status --short
Get-Content .gitignore
```

`.gitignore` 里必须包含：

```gitignore
.env
.env.local
DEPLOY_ENV.txt
node_modules/
dist/
venv/
.venv/
```

本地准备好这些真实密钥，后面会填到 ECS：

- `backend/.env`
- `frontend/.env.local`
- Supabase Service Role Key
- Supabase Anon Key
- DeepSeek API Key
- Resend API Key

## 二、域名 DNS

在阿里云域名控制台添加解析：

| 主机记录 | 类型 | 记录值 |
|---|---|---|
| `@` | A | `123.57.180.79` |
| `www` | A | `123.57.180.79` |

解析生效后，在本地检查：

```powershell
nslookup mede-in-ai.com
nslookup www.mede-in-ai.com
```

返回 IP 应该是 `123.57.180.79`。

## 三、ECS 安全组

在阿里云控制台打开 ECS 实例的安全组，入方向放行：

| 协议 | 端口 | 来源 |
|---|---:|---|
| TCP | 22 | 你的办公 IP，临时也可用 `0.0.0.0/0` |
| TCP | 80 | `0.0.0.0/0` |
| TCP | 443 | `0.0.0.0/0` |

不要开放 `8000`，后端只给本机 Nginx 访问。

## 四、登录服务器并安装环境

```bash
ssh root@123.57.180.79
```

在服务器执行：

```bash
apt update
apt install -y git curl wget nginx python3 python3-pip python3-venv unzip ca-certificates
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
python3 --version
node --version
nginx -v
```

要求：

- Python `3.10+`
- Node.js `20.x`
- Nginx 已安装

## 五、拉取代码

```bash
mkdir -p /var/www
cd /var/www
git clone https://github.com/phuxulphacggavcls-glitch/ai-secretary.git
cd /var/www/ai-secretary
```

如果仓库是私有仓库，需要先在服务器配置 GitHub SSH Key 或用 GitHub Personal Access Token。

## 六、配置后端环境变量

创建文件：

```bash
nano /var/www/ai-secretary/backend/.env
```

填入：

```env
SUPABASE_URL=https://你的项目.supabase.co
SUPABASE_SERVICE_KEY=你的-service-role-key
DEEPSEEK_API_KEY=你的-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
RESEND_API_KEY=你的-resend-api-key
FROM_EMAIL=secretary@mede-in-ai.com
SECRET_KEY=至少32位随机字符串
FRONTEND_URL=https://mede-in-ai.com
```

注意：代码读取的是 `SECRET_KEY`，不是 `JWT_SECRET`。

## 七、启动后端

```bash
cd /var/www/ai-secretary/backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

创建 systemd 服务：

```bash
cat > /etc/systemd/system/ai-secretary.service <<'EOF'
[Unit]
Description=AI Secretary Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/var/www/ai-secretary/backend
EnvironmentFile=/var/www/ai-secretary/backend/.env
ExecStart=/var/www/ai-secretary/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable ai-secretary
systemctl start ai-secretary
systemctl status ai-secretary --no-pager
curl http://127.0.0.1:8000/health
```

看到 `{"status":"ok"}` 就说明后端正常。

## 八、构建前端

创建生产环境变量：

```bash
cat > /var/www/ai-secretary/frontend/.env.production <<'EOF'
VITE_SUPABASE_URL=https://你的项目.supabase.co
VITE_SUPABASE_ANON_KEY=你的-anon-key
VITE_API_BASE_URL=/api
EOF
```

构建：

```bash
cd /var/www/ai-secretary/frontend
npm ci
npm run build
```

成功后会生成：

```text
/var/www/ai-secretary/frontend/dist
```

## 九、配置 Nginx

```bash
cat > /etc/nginx/sites-available/ai-secretary <<'EOF'
server {
    listen 80;
    server_name mede-in-ai.com www.mede-in-ai.com 123.57.180.79;

    root /var/www/ai-secretary/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/ai-secretary /etc/nginx/sites-enabled/ai-secretary
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

先验证 HTTP：

```bash
curl http://127.0.0.1/api/health
```

本地浏览器访问：

```text
http://mede-in-ai.com
http://mede-in-ai.com/api/health
```

## 十、配置 HTTPS

DNS 已经解析到 ECS 后，执行：

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d mede-in-ai.com -d www.mede-in-ai.com
certbot renew --dry-run
```

完成后验证：

```text
https://mede-in-ai.com
https://mede-in-ai.com/api/health
```

## 十一、让朋友访问前的检查

用手机流量访问，不要只用服务器或本机 Wi-Fi 测：

1. 打开 `https://mede-in-ai.com`
2. 注册或登录测试账号
3. 输入 `明天下午提醒我给客户报价`
4. 确认解析结果
5. 保存任务
6. 进入任务列表，确认任务存在
7. 标记完成，确认状态能更新

## 十二、更新代码

以后改完代码并推到 GitHub 后，在服务器执行：

```bash
cd /var/www/ai-secretary
git pull

cd backend
source venv/bin/activate
pip install -r requirements.txt
systemctl restart ai-secretary

cd ../frontend
npm ci
npm run build
systemctl reload nginx
```

## 十三、常用排错命令

后端：

```bash
systemctl status ai-secretary --no-pager
journalctl -u ai-secretary -n 100 --no-pager
systemctl restart ai-secretary
curl http://127.0.0.1:8000/health
```

Nginx：

```bash
nginx -t
tail -100 /var/log/nginx/error.log
systemctl reload nginx
```

前端：

```bash
cd /var/www/ai-secretary/frontend
npm run build
grep -R "VITE_API_BASE_URL" .env.production
```

接口：

```bash
curl -i https://mede-in-ai.com/api/health
```

## 十四、关键注意事项

- `VITE_API_BASE_URL` 在 ECS 上建议写 `/api`，这样前后端同域，跨域问题最少。
- `FRONTEND_URL` 必须写正式域名 `https://mede-in-ai.com`。
- `SECRET_KEY` 变量名必须和代码一致。
- `SUPABASE_SERVICE_KEY` 只能放后端，不能放前端。
- `8000` 不要对公网开放。
- 邮件提醒如果要用 `secretary@mede-in-ai.com`，还需要在 Resend 配置并验证发信域名的 DNS 记录。
- 如果 Supabase 在国内访问不稳定，MVP 可以先跑通；后续再评估迁移到国内 PostgreSQL + 自建登录。
