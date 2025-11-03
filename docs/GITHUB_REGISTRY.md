# GitHub Container Registry Setup Guide

## 🚀 Quick Setup

### 1. Enable GitHub Actions

Your workflow is already created at `.github/workflows/docker-publish.yml`

### 2. Push to GitHub

```bash
git add .
git commit -m "Add Docker build workflow"
git push origin main
```

The workflow will automatically:

- ✅ Build your Docker image
- ✅ Push to GitHub Container Registry (ghcr.io)
- ✅ Tag with branch name, commit SHA, and `latest`

### 3. View Your Image

After the workflow runs, find your image at:

```
ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest
```

Visit: `https://github.com/YOUR-USERNAME/a2a-news-tracker/pkgs/container/a2a-news-tracker`

---

## 📦 Using Your Published Image

### Pull and Run

```bash
# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR-USERNAME --password-stdin

# Pull the image
docker pull ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest

# Run it
docker run -d \
  --name a2a-api \
  -p 8000:8000 \
  --env-file .env \
  ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest
```

### Update docker-compose.yml

Replace `build: .` with your published image:

```yaml
services:
  app:
    image: ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest
    container_name: crypto_forex_a2a
    env_file: .env
    ports:
      - "8000:8000"
    restart: always
```

---

## 🔒 Make Image Public (Optional)

By default, images are private. To make public:

1. Go to: `https://github.com/YOUR-USERNAME?tab=packages`
2. Click your `a2a-news-tracker` package
3. Click **Package settings**
4. Scroll to **Danger Zone**
5. Click **Change visibility** → **Public**

Now anyone can pull without authentication:

```bash
docker pull ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest
```

---

## 🏷️ Version Tags

The workflow creates multiple tags automatically:

### On push to main:

- `ghcr.io/.../a2a-news-tracker:latest`
- `ghcr.io/.../a2a-news-tracker:main`
- `ghcr.io/.../a2a-news-tracker:main-abc1234` (commit SHA)

### On version tag (e.g., `v1.0.0`):

```bash
git tag v1.0.0
git push origin v1.0.0
```

Creates:

- `ghcr.io/.../a2a-news-tracker:1.0.0`
- `ghcr.io/.../a2a-news-tracker:1.0`
- `ghcr.io/.../a2a-news-tracker:latest`

---

## 🔐 Personal Access Token (for local push)

If you want to push manually from your computer:

### 1. Create Token

1. Go to: `https://github.com/settings/tokens/new`
2. Select scopes: `write:packages`, `read:packages`, `delete:packages`
3. Generate token and copy it

### 2. Login to Registry

```bash
export CR_PAT=YOUR_TOKEN
echo $CR_PAT | docker login ghcr.io -u YOUR-USERNAME --password-stdin
```

### 3. Build and Push

```bash
# Build with proper tag
docker build -t ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest .

# Push to registry
docker push ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest
```

---

## 🎯 Workflow Triggers

The workflow runs on:

| Event                    | Description                     |
| ------------------------ | ------------------------------- |
| `push` to main/master    | Auto-build on every commit      |
| `tag` starting with `v*` | Version releases (v1.0.0)       |
| `pull_request`           | Test builds on PRs              |
| `workflow_dispatch`      | Manual trigger from Actions tab |

### Manual Trigger

1. Go to: **Actions** tab on GitHub
2. Select **Build and Push Docker Image**
3. Click **Run workflow**
4. Choose branch and click **Run**

---

## 📊 View Build Status

Add a badge to your README.md:

```markdown
![Docker Build](https://github.com/YOUR-USERNAME/a2a-news-tracker/actions/workflows/docker-publish.yml/badge.svg)
```

---

## 🚢 Deploy to Production

### Using Docker Compose on Server

```bash
# SSH to your server
ssh user@your-server.com

# Create docker-compose.yml
cat > docker-compose.yml <<EOF
services:
  app:
    image: ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest
    ports:
      - "8000:8000"
    environment:
      - PORT=8000
      - REDIS_URL=redis://your-redis-url
      - GEMINI_API_KEY=your-key
      # ... other env vars
    restart: always
EOF

# Deploy
docker-compose up -d

# Update to latest
docker-compose pull && docker-compose up -d
```

### Using Cloud Platforms

**Render:**

- Image URL: `ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest`
- Add environment variables in dashboard

**Railway:**

```bash
railway up --service a2a-api
```

**Fly.io:**

```bash
fly deploy --image ghcr.io/YOUR-USERNAME/a2a-news-tracker:latest
```

---

## 🔄 Auto-Deploy on Push

Set up continuous deployment:

1. **On your server**, create update script:

```bash
#!/bin/bash
cd /app
docker-compose pull
docker-compose up -d
```

2. **Use webhook** or **GitHub Actions deploy job**:

```yaml
- name: Deploy to server
  uses: appleboy/ssh-action@master
  with:
    host: ${{ secrets.SERVER_HOST }}
    username: ${{ secrets.SERVER_USER }}
    key: ${{ secrets.SSH_PRIVATE_KEY }}
    script: |
      cd /app
      docker-compose pull
      docker-compose up -d
```

---

## 📝 Summary

**What you get:**

- ✅ Automatic Docker builds on every push
- ✅ Free hosting on GitHub Container Registry
- ✅ Version tagging with git tags
- ✅ Easy deployment anywhere
- ✅ No Docker Hub rate limits

**Next steps:**

1. Push code to GitHub
2. Check Actions tab for build status
3. Find image at `ghcr.io/YOUR-USERNAME/a2a-news-tracker`
4. Deploy anywhere! 🚀
