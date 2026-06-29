#!/bin/bash
# Adds ax-server (port 8000) as a reverse proxy under api.capitalintelligence.online/ax/
# Result: https://api.capitalintelligence.online/ax/api/v1/health
set -euo pipefail

NGINX_CONF="/var/www/capital-intelligence/proxy/nginx.conf"

# Backup original
cp "$NGINX_CONF" "${NGINX_CONF}.bak.$(date +%s)"

# Write the updated config
cat > "$NGINX_CONF" << 'NGINX_EOF'
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    sendfile on;
    keepalive_timeout 65;

    upstream frontend_app {
        server frontend:80;
    }

    upstream generator_app {
        server generator:80;
    }

    upstream backend_api {
        server backend:8001;
    }

    upstream dmaas_api {
        server 74.208.213.94:3302;
    }

    upstream ax_server_api {
        server 74.208.213.94:8000;
    }

    # Catch-all default block redirects/handles raw IP traffic
    server {
        listen 80 default_server;
        listen 443 ssl default_server;
        server_name _;

        ssl_certificate /etc/letsencrypt/live/capitalintelligence.online/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/capitalintelligence.online/privkey.pem;

        location / {
            proxy_pass http://frontend_app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }

    # Main Brand Website
    server {
        listen 80;
        server_name capitalintelligence.online www.capitalintelligence.online;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl;
        server_name capitalintelligence.online www.capitalintelligence.online;

        ssl_certificate /etc/letsencrypt/live/capitalintelligence.online/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/capitalintelligence.online/privkey.pem;

        location / {
            proxy_pass http://frontend_app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }

    # Command Center / Generator Subdomain
    server {
        listen 80;
        listen 443 ssl;
        server_name generator.capitalintelligence.online;

        ssl_certificate /etc/letsencrypt/live/capitalintelligence.online/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/capitalintelligence.online/privkey.pem;

        location / {
            proxy_pass http://generator_app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }

    # Direct Backend API Subdomain
    server {
        listen 80;
        listen 443 ssl;
        server_name api.capitalintelligence.online;

        ssl_certificate /etc/letsencrypt/live/capitalintelligence.online/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/capitalintelligence.online/privkey.pem;

        # AthleteX ax-server API (port 8000)
        location /ax/ {
            proxy_pass http://ax_server_api/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        location /tasks {
            proxy_pass http://dmaas_api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        location / {
            proxy_pass http://backend_api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }

    # DMAAS API Subdomain
    server {
        listen 80;
        listen 443 ssl;
        server_name dmaas.capitalintelligence.online;

        ssl_certificate /etc/letsencrypt/live/capitalintelligence.online/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/capitalintelligence.online/privkey.pem;

        location / {
            proxy_pass http://dmaas_api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
NGINX_EOF

echo "✅ nginx.conf updated."

# Rebuild and restart just the proxy container
cd /var/www/capital-intelligence
docker compose build proxy
docker compose up -d proxy

echo "✅ Proxy rebuilt and restarted. Testing in 3s..."
sleep 3
curl -s https://api.capitalintelligence.online/ax/api/v1/health || echo "⚠️  Health check failed"
