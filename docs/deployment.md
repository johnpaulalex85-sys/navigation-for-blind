# AIDEN Production Deployment Guide

This document describes how to deploy the **AIDEN Indoor Navigation Assistant** in a production environment.

---

## Production Security Requirements (SSL/HTTPS)
> [!IMPORTANT]
> Modern web browsers restrict access to `navigator.mediaDevices.getUserMedia` (webcam & microphone) and the `SpeechSynthesis` API to **secure contexts** only (i.e. `localhost` or domains served over `HTTPS`). 
> You MUST configure SSL/TLS certificates (e.g., Let's Let'sEncrypt) for production deployment.

---

## Deployment Option A: Using Docker Compose (Recommended)

Docker Compose is the fastest way to compile and run the application in an isolated environment.

1. Ensure **Docker** and **Docker Compose** are installed on the production host.
2. Navigate to the project root:
   ```bash
   cd "D:\main project\Building navigation\AIDEN"
   ```
3. Build and launch the container in detached (background) mode:
   ```bash
   docker-compose up -d --build
   ```
4. Verify the container status:
   ```bash
   docker ps
   ```
   You should see `aiden_assistant` running and routing port `5000`.

---

## Deployment Option B: Manual Production Setup (WSGI + Eventlet/Gunicorn)

To run without Docker using a production WSGI server (Gunicorn):

1. Set up your production variables:
   ```bash
   export FLASK_ENV=production
   export SECRET_KEY="your_complex_secret_key"
   ```
2. Install a production-ready server supporting WebSockets. Since Flask-SocketIO runs best under `gunicorn` with the `eventlet` or `gevent` worker, install it:
   ```bash
   pip install gunicorn eventlet
   ```
3. Launch gunicorn:
   ```bash
   gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 app:app
   ```
   *Note: Due to OpenCV frame processing constraints, a single worker (`-w 1`) is recommended to avoid thread-blocking conflicts on SQLite and OpenCV instances.*

---

## Production Reverse Proxy Setup (Nginx Config)

It is highly recommended to put Nginx in front of the Flask app to terminate SSL certificates and manage WebSocket upgrade headers. Here is a sample block configuration:

```nginx
server {
    listen 80;
    server_name aiden.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name aiden.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/aiden.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aiden.yourdomain.com/privkey.pem;

    # Standard proxy settings
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Crucial config for Socket.IO WebSockets upgrades
    location /socket.io/ {
        proxy_pass http://127.0.0.1:5000/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }
}
```

---

## Data Persistence & Backup
The SQLite database is located inside the container at `/app/database/aiden.db`. Because the database directory is volume-mounted in `docker-compose.yml` (`./database:/app/database`), your building data, rooms, and nodes are saved locally on the host system and will persist across container rebuilds.
To perform backups, copy `database/aiden.db` to a secure backup directory.
