# MUSKU — Free Deployment Guide

MUSKU runs as a single Python process that serves BOTH the web UI/API (port 8000)
and the Live voice WebSocket (port 8770). It needs a real compute runtime (not
just static hosting) because the AI + WebSocket live on the server.

## What works FREE (runs the full app AS-IS)

### 1. Oracle Cloud "Always Free"  — BEST, always-on, $0 forever
- 2 AMD VMs (1/8 OCPU, 1 GB RAM) OR up to 4 ARM VMs (24 GB total). Never sleeps.
- Native Linux → `python app.py` directly (no Docker needed), or run the container.
- WebSockets + outbound Gemini calls allowed. Block storage is persistent
  (user data in `musku_users/<uid>/` survives restarts).
- Signup needs a card but stays $0 on always-free shapes.
- Steps:
  1. Create Always Free VM (Ubuntu). Open ports 8000, 8770 in the VCN security list.
  2. `git clone` / `scp` the `musku-2.0` folder.
  3. `pip install -r requirements-server.txt`
  4. `REQUIRE_AUTH=true MUSKU_LIVE_WS_HOST=0.0.0.0 PORT=8000 python app.py &`
  5. Put it behind `nginx` + Let's Encrypt (HTTPS/WSS) for production.
  6. Set `ALLOWED_ORIGIN=https://your-domain`.

### 2. Fly.io free tier  — 3 always-on VMs, free
- 3 shared-CPU VMs (256 MB RAM each) + 3 GB persistent volume (free).
- Supports WebSockets, outbound internet, volumes (user data persists).
- Build with the included `Dockerfile`: `fly launch` → `fly deploy`.
- Steps:
  1. `fly launch` (uses Dockerfile), set `internal_port 8000`.
  2. `fly volumes create musku_data 3` and mount to `/app/musku_users` (persist data).
  3. Set secrets: `fly secrets set REQUIRE_AUTH=true ALLOWED_ORIGIN=https://<app>.fly.dev`.
  4. `fly deploy`.
  Note: the WS (8770) and HTTP (8000) run in one container; expose both.

## What does NOT work free / alone

- **Firebase Hosting (`*.web.app`)** — serves only static files. Your Python
  backend (AI + WebSocket) will NOT run there. You'd still need Cloud Run
  (Blaze/paid) for the backend. Firebase Hosting ≠ a server.
- **Render free** — works for HTTP `/api/chat` but the free tier SLEEPS → the
  Live voice WebSocket drops/disconnects. Not reliable for voice.
- **PythonAnywhere free** — no WebSocket support → `/live` voice won't work.
- **Google Cloud Run free tier** — works, but a persistent voice WebSocket burns
  the free quota fast; effectively needs Blaze for steady use.

## One-command Oracle setup (recommended)
Everything above is wrapped in `deploy/oracle_setup.sh` + `deploy/musku.service`
+ `deploy/nginx_musku.conf`. After you have the VM and the `musku-2.0` folder
on it (e.g. at `/opt/musku/musku-2.0`), run as root:

```bash
# with a domain (recommended — gets free TLS via certbot):
sudo bash deploy/oracle_setup.sh /opt/musku/musku-2.0 your.domain.com

# or without a domain yet (http://<VM-IP>:8000):
sudo bash deploy/oracle_setup.sh /opt/musku/musku-2.0 ""
```

The script installs deps, creates a venv, installs `requirements-server.txt`,
registers the systemd service (auto-restart), and (with a domain) configures
nginx + Let's Encrypt and proxies:
- `/` → app.py HTTP (8000)  — serves the UI + `/api/chat`
- `/live` → app.py WebSocket (8770) — the voice stream

Frontend note: `index.html` now connects to same-origin `/live` on deployed
(HTTPS) hosts, and to `:8770` only in local dev. No code change needed per
deploy — nginx handles TLS + WebSocket upgrade.

## Limits to expect on free tiers
- RAM/CPU bound → realistically **tens to low-hundreds** of concurrent users,
  NOT thousands. The per-user Gemini key means no shared LLM quota.
- Free VMs are small; if you outgrow them, move to a paid VPS (Hetzner ~₹400/mo)
  or scale Cloud Run + Postgres — the storage layer (`user_context`/`memory.paths`)
  is already decoupled for that migration.

## Pre-deploy checklist
- [ ] `requirements-server.txt` installed (NOT the desktop `requirements.txt`).
- [ ] `REQUIRE_AUTH=true`, `ALLOWED_ORIGIN` set.
- [ ] HTTPS/WSS in front (tokens + per-user keys travel in headers).
- [ ] Persistent volume mounted at `/app/musku_users` so user data survives restarts.
- [ ] Frontend `liveWsUrl` points to the deployed host (not 127.0.0.1).
