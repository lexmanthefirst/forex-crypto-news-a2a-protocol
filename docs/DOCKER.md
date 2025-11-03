# Docker Deployment Guide

## Quick Start

### 1. Build and Run with Docker Compose (Recommended)

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

The API will be available at `http://localhost:8000`

### 2. Build and Run with Docker Only

```bash
# Build the image
docker build -t a2a-market-api .

# Run Redis separately
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Run the API
docker run -d \
  --name a2a-api \
  -p 8000:8000 \
  --env-file .env \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  a2a-market-api

# View logs
docker logs -f a2a-api
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Required API Keys
ALPHAVANTAGE_API_KEY=your_key_here
NEWSAPI_API_KEY=your_key_here
CRYPTOPANIC_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here

# Optional
COINGECKO_API_KEY=
NOTIFIER_WEBHOOK=https://your-webhook-url.com

# Scheduler
POLL_INTERVAL_MINUTES=15
WATCHLIST=BTC,ETH,EUR/USD

# Notifications
ENABLE_NOTIFICATIONS=true
NOTIFICATION_COOLDOWN_SECONDS=900
ANALYSIS_IMPACT_THRESHOLD=0.5
```

## Testing the Deployment

```bash
# Health check
curl http://localhost:8000/health

# Test analysis
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "kind": "message",
        "role": "user",
        "parts": [{"kind": "text", "text": "Analyze BTC"}]
      }
    }
  }'

# View API documentation
open http://localhost:8000/docs
```

## Production Deployment

### Using Docker Compose (Cloud VM)

```bash
# On your server
git clone <your-repo>
cd a2a-news-tracker

# Set production environment variables
nano .env

# Deploy
docker-compose up -d

# Enable auto-restart
docker-compose up -d --restart unless-stopped
```

### Using Container Registries

```bash
# Tag and push to Docker Hub
docker tag a2a-market-api yourusername/a2a-market-api:latest
docker push yourusername/a2a-market-api:latest

# Or push to GitHub Container Registry
docker tag a2a-market-api ghcr.io/yourusername/a2a-market-api:latest
docker push ghcr.io/yourusername/a2a-market-api:latest
```

### Deploy to Cloud Platforms

#### Render
1. Connect your GitHub repo
2. Select "Docker" as environment
3. Add environment variables from `.env`
4. Deploy

#### Railway
```bash
railway login
railway init
railway up
```

#### Fly.io
```bash
fly launch
fly secrets set GEMINI_API_KEY=xxx NEWSAPI_API_KEY=yyy ...
fly deploy
```

#### AWS ECS / Azure Container Instances / Google Cloud Run
- Push image to ECR/ACR/GCR
- Create task definition with environment variables
- Deploy service with Redis connection

## Monitoring

### View Logs
```bash
# All services
docker-compose logs -f

# Just the API
docker-compose logs -f api

# Last 100 lines
docker-compose logs --tail=100 api
```

### Check Container Status
```bash
docker-compose ps
docker stats
```

### Debug Inside Container
```bash
docker-compose exec api /bin/bash
docker-compose exec redis redis-cli
```

## Troubleshooting

### Port Already in Use
```bash
# Change port in docker-compose.yml
ports:
  - "8080:8000"  # Use port 8080 instead
```

### Redis Connection Failed
```bash
# Check Redis is running
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli ping
```

### API Not Starting
```bash
# Check logs
docker-compose logs api

# Verify environment variables
docker-compose exec api env | grep API_KEY
```

### Restart Services
```bash
# Restart just the API
docker-compose restart api

# Restart everything
docker-compose restart
```

## Scaling

```bash
# Run multiple API instances
docker-compose up -d --scale api=3
```

## Cleanup

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (clears Redis data)
docker-compose down -v

# Remove images
docker rmi a2a-market-api
```
