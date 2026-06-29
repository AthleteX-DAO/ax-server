#!/bin/bash
set -euo pipefail
ENV_FILE="/opt/ax-server/.env"
OLD="CORS_ORIGINS=https://app.athletex.io,https://stage.athletex.io,http://74.208.213.94,http://localhost:3000,http://localhost:8080"
NEW="CORS_ORIGINS=https://app.athletex.io,https://stage.athletex.io,https://athletex-prod.web.app,https://api.capitalintelligence.online,http://74.208.213.94,http://localhost:3000,http://localhost:8080"
sed -i "s|$OLD|$NEW|" "$ENV_FILE"
echo "✅ CORS updated. Restarting ax-server..."
cd /opt/ax-server
docker compose restart ax-server
sleep 3
echo "✅ ax-server restarted."
curl -s https://api.capitalintelligence.online/ax/api/v1/health || echo "⚠️ Health check failed"
