# Aliyun ECS Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy AI Secretary to an ICP-approved domestic domain on Alibaba Cloud ECS so invited friends can access it reliably from China.

**Architecture:** Keep Supabase as the database/auth provider for this MVP. Run FastAPI on ECS behind Nginx at `/api/`, serve the Vite React build as static files from Nginx, and use systemd to keep the backend alive.

**Tech Stack:** Ubuntu 22.04, Nginx, systemd, Python virtualenv, Node.js 20, FastAPI, React/Vite, Supabase, DeepSeek, Resend.

---

### Task 1: Prepare Code For ECS

**Files:**
- Read: `backend/config.py`
- Read: `backend/main.py`
- Read: `frontend/src/api.js`
- Create: `国内部署_阿里云ECS_操作手册.md`

- [ ] **Step 1: Confirm backend environment variable names**

Run from repository root:

```powershell
Get-Content -LiteralPath backend\config.py
```

Expected: the backend reads `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `RESEND_API_KEY`, `FROM_EMAIL`, `SECRET_KEY`, and `FRONTEND_URL`.

- [ ] **Step 2: Confirm the frontend can use a same-origin API path**

Run from repository root:

```powershell
Get-Content -LiteralPath frontend\src\api.js
```

Expected: the frontend reads `VITE_API_BASE_URL`. For ECS production, set it to `/api` so the same domain serves frontend and backend.

- [ ] **Step 3: Save the corrected ECS guide**

Create `国内部署_阿里云ECS_操作手册.md` with exact server setup, Nginx, systemd, HTTPS, update, and rollback commands.

### Task 2: Deploy Backend On ECS

**Files:**
- Create on server: `/var/www/ai-secretary/backend/.env`
- Create on server: `/etc/systemd/system/ai-secretary.service`

- [ ] **Step 1: SSH into ECS**

Run from a local terminal:

```bash
ssh root@123.57.180.79
```

Expected: the shell prompt changes to the ECS server.

- [ ] **Step 2: Install runtime packages**

Run on ECS:

```bash
apt update
apt install -y git curl wget nginx python3 python3-pip python3-venv unzip ca-certificates
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
python3 --version
node --version
nginx -v
```

Expected: Python is 3.10 or newer, Node.js is 20.x, and Nginx is installed.

- [ ] **Step 3: Pull the repository**

Run on ECS:

```bash
mkdir -p /var/www
cd /var/www
git clone https://github.com/phuxulphacggavcls-glitch/ai-secretary.git
cd /var/www/ai-secretary
```

Expected: the project exists at `/var/www/ai-secretary`.

- [ ] **Step 4: Create backend environment file**

Run on ECS and paste the real values from the local secret files:

```bash
nano /var/www/ai-secretary/backend/.env
```

Required content shape:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
RESEND_API_KEY=your-resend-api-key
FROM_EMAIL=secretary@mede-in-ai.com
SECRET_KEY=a-random-string-at-least-32-characters
FRONTEND_URL=https://mede-in-ai.com
```

- [ ] **Step 5: Install backend dependencies**

Run on ECS:

```bash
cd /var/www/ai-secretary/backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Expected: dependencies install without errors.

- [ ] **Step 6: Create the systemd service**

Run on ECS:

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
curl http://127.0.0.1:8000/health
```

Expected: `curl` returns `{"status":"ok"}`.

### Task 3: Deploy Frontend And Nginx

**Files:**
- Create on server: `/var/www/ai-secretary/frontend/.env.production`
- Create on server: `/etc/nginx/sites-available/ai-secretary`

- [ ] **Step 1: Build the frontend**

Run on ECS:

```bash
cat > /var/www/ai-secretary/frontend/.env.production <<'EOF'
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_API_BASE_URL=/api
EOF
cd /var/www/ai-secretary/frontend
npm ci
npm run build
```

Expected: `frontend/dist` is generated.

- [ ] **Step 2: Configure Nginx**

Run on ECS:

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

Expected: `nginx -t` reports syntax OK.

- [ ] **Step 3: Enable HTTPS**

Run on ECS after DNS A records point to `123.57.180.79`:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d mede-in-ai.com -d www.mede-in-ai.com
certbot renew --dry-run
```

Expected: `https://mede-in-ai.com` opens the AI Secretary frontend and `https://mede-in-ai.com/api/health` returns `{"status":"ok"}`.

### Task 4: Verify Friend Access

**Files:**
- Read only: production site

- [ ] **Step 1: Test from phone network**

Open on mobile data:

```text
https://mede-in-ai.com
```

Expected: login page loads without browser security warnings.

- [ ] **Step 2: Test the core workflow**

Use a test account and enter:

```text
明天下午提醒我给客户报价
```

Expected: the parse confirmation dialog appears, the task saves, and it appears in the task list.

- [ ] **Step 3: Check backend logs if anything fails**

Run on ECS:

```bash
journalctl -u ai-secretary -n 100 --no-pager
tail -100 /var/log/nginx/error.log
```

Expected: errors identify either missing environment variables, Supabase credentials, Nginx proxy issues, or frontend build misconfiguration.
