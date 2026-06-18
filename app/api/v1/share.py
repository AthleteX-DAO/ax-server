"""Share card endpoints — upload athlete card images and serve OG-tagged pages.

POST /api/v1/share-card  → upload PNG, get back a share URL
GET  /share/{card_id}    → HTML page with og:image for social crawlers
GET  /share/{card_id}/image → raw PNG
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

# Store images in a local directory. Swap to S3/GCS in production.
SHARE_DIR = Path("share_cards")
SHARE_DIR.mkdir(exist_ok=True)

router = APIRouter(tags=["share"])


class ShareCardResponse(BaseModel):
    card_id: str
    share_url: str
    image_url: str


@router.post("/share-card", response_model=ShareCardResponse)
async def create_share_card(
    image: UploadFile = File(...),
    name: str = Form(...),
    rank: int = Form(...),
    category: str = Form(""),
    elo: str = Form("0"),
    record: str = Form("0-0"),
    win_pct: str = Form("0.0"),
):
    """Accept a PNG upload and metadata, return a shareable URL."""
    contents = await image.read()

    # Deterministic ID from name + rank so resharing overwrites
    raw = f"{name.lower().strip()}:{rank}:{category}"
    card_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

    # Save image
    img_path = SHARE_DIR / f"{card_id}.png"
    img_path.write_bytes(contents)

    # Save metadata as a simple text sidecar
    meta_path = SHARE_DIR / f"{card_id}.meta"
    meta_path.write_text(
        f"{name}\n{rank}\n{category}\n{elo}\n{record}\n{win_pct}"
    )

    # TODO: replace with real domain in production
    base = "https://api.athletex.io"
    return ShareCardResponse(
        card_id=card_id,
        share_url=f"{base}/share/{card_id}",
        image_url=f"{base}/share/{card_id}/image",
    )


@router.get("/share/{card_id}/image")
async def get_share_image(card_id: str):
    """Serve the raw PNG for og:image crawlers."""
    img_path = SHARE_DIR / f"{card_id}.png"
    if not img_path.exists():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(
        img_path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/share/{card_id}", response_class=HTMLResponse)
async def get_share_page(card_id: str):
    """Serve an HTML page with Open Graph tags for social media crawlers.

    When Twitter/Facebook see a link to this page, they will:
    1. Fetch this HTML
    2. Read og:image, og:title, og:description
    3. Render a rich preview card with the athlete's stats image
    """
    meta_path = SHARE_DIR / f"{card_id}.meta"
    if not meta_path.exists():
        return HTMLResponse("Card not found", status_code=404)

    lines = meta_path.read_text().strip().split("\n")
    name = lines[0] if len(lines) > 0 else "Athlete"
    rank = lines[1] if len(lines) > 1 else "?"
    category = lines[2] if len(lines) > 2 else ""
    elo = lines[3] if len(lines) > 3 else "0"
    record = lines[4] if len(lines) > 4 else "0-0"
    win_pct = lines[5] if len(lines) > 5 else "0.0"

    # TODO: replace with real domain
    base = "https://api.athletex.io"
    image_url = f"{base}/share/{card_id}/image"
    page_url = f"{base}/share/{card_id}"
    app_url = "https://app.athletex.io/versus"

    title = f"{name} — #{rank} Ranked | AthleteX"
    description = (
        f"{name} is ranked #{rank} in {category} on AthleteX. "
        f"ELO: {elo} | Record: {record} | Win%: {win_pct}% "
        f"Do you agree? Vote now!"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{title}</title>

    <!-- Open Graph (Facebook, LinkedIn, Discord) -->
    <meta property="og:type" content="website">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:image" content="{image_url}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:url" content="{page_url}">
    <meta property="og:site_name" content="AthleteX">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{description}">
    <meta name="twitter:image" content="{image_url}">
    <meta name="twitter:site" content="@AthleteX_io">

    <!-- Auto-redirect humans to the app -->
    <meta http-equiv="refresh" content="2;url={app_url}">
    <style>
        body {{
            background: #0D0D0D;
            color: #FFC600;
            font-family: 'Helvetica Neue', sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            text-align: center;
        }}
        .card {{ max-width: 500px; padding: 40px; }}
        h1 {{ font-size: 28px; margin-bottom: 8px; }}
        p {{ color: #999; font-size: 16px; }}
        a {{ color: #FFC600; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{name}</h1>
        <p>#{rank} Ranked in {category}</p>
        <p>Redirecting to AthleteX...</p>
        <p><a href="{app_url}">Vote now →</a></p>
    </div>
</body>
</html>"""
    return HTMLResponse(html)
