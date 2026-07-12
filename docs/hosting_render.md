# Hosting AIDEN on Render

This guide outlines how to deploy the **AIDEN Indoor Navigation Assistant** to **Render** (https://render.com).

---

## Why Render is Perfect for AIDEN
1. **Free/Automatic SSL (HTTPS)**: Modern browsers block access to webcams and microphones on standard `http://` sites. Render provides a free `https://` domain out of the box, satisfying browser security criteria.
2. **Docker Support**: Because EasyOCR and OpenCV require native system libraries (like `libGL` and `libglib`), standard Python environments might fail to compile them. Render can build and execute our `Dockerfile` directly, guaranteeing all dependencies run correctly.
3. **Persistent Disks**: Render allows mounting a persistent storage volume, ensuring that your SQLite database (`aiden.db`) and uploaded building blueprints are not erased when the web service restarts.

---

## Method 1: Automatic Deploy using Blueprint (`render.yaml`)

We have pre-configured a `render.yaml` file in the project root. This file tells Render exactly how to construct the server.

1. **Push your code to GitHub/GitLab**:
   Create a repository and commit all files in the `AIDEN/` directory (make sure `.gitignore` excludes `venv/` or cached database files, but holds `render.yaml` and the subfolders).
2. **Go to Render**:
   Sign in to [Render Dashboard](https://dashboard.render.com).
3. **Initialize Blueprint**:
   * Click **New** (top right) -> **Blueprint**.
   * Connect your GitHub repository.
   * Render will automatically discover `render.yaml` and set up:
     * A web service named `aiden-indoor-navigation`.
     * A persistent storage disk named `aiden-storage` mounted at `/app/database`.
     * A generated secure `SECRET_KEY`.
4. **Approve & Deploy**:
   Click **Approve** on the Render dashboard. Render will build the Docker container and launch the server.

---

## Method 2: Manual Deploy (Docker Web Service)

If you prefer to configure the deployment manually through Render's web interface:

1. Push your repository to GitHub.
2. In Render, click **New** -> **Web Service**.
3. Connect your repository.
4. Set the following parameters:
   * **Language / Runtime**: `Docker`
   * **Region**: Choose the region closest to your target audience.
   * **Branch**: `main` (or your active branch)
5. Expand **Advanced** and configure:
   * **Add Environment Variables**:
     * `FLASK_ENV` = `production`
     * `FLASK_DEBUG` = `False`
     * `SECRET_KEY` = `your_own_custom_secret_string`
   * **Add Persistent Disk**:
     * **Name**: `aiden-db-disk`
     * **Mount Path**: `/app/database`
     * **Size**: `1 GiB` (more than enough for SQLite logs)
6. Click **Create Web Service**.

---

## WebSockets Configuration

Render's Web Services support WebSockets natively. Once deployed, the frontend JavaScript in `static/js/main.js` will automatically connect to the secure WebSocket (`wss://`) using Render's proxy. No additional socket configuration is required!
