"""Comment endpoints for prediction markets."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.auth.deps import RequireAuth, OptionalAuth
from app.config import Settings
from app.deps import SettingsDep
from app.models.trading import Comment, CreateCommentRequest

router = APIRouter(prefix="/comments", tags=["comments"])

_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "comments"


def _comments_path(market_id: int) -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR / f"{market_id}.json"


def _load(market_id: int) -> list[dict]:
    p = _comments_path(market_id)
    if not p.exists():
        return []
    return json.loads(p.read_text())


def _save(market_id: int, comments: list[dict]):
    _comments_path(market_id).write_text(json.dumps(comments, indent=2))


@router.get("/{market_id}", response_model=list[Comment])
async def list_comments(market_id: int, limit: int = 50, offset: int = 0):
    comments = _load(market_id)
    comments.sort(key=lambda c: c["timestamp"], reverse=True)
    return comments[offset:offset + limit]


@router.post("/{market_id}", response_model=Comment)
async def post_comment(
    market_id: int,
    body: CreateCommentRequest,
    wallet: RequireAuth,
):
    comment = Comment(
        id=str(uuid.uuid4()),
        market_id=market_id,
        wallet=wallet,
        text=body.text.strip(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    comments = _load(market_id)
    comments.append(comment.model_dump())
    _save(market_id, comments)
    return comment


@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: str,
    wallet: RequireAuth,
):
    # Search all market files for the comment
    for p in _DATA_DIR.glob("*.json"):
        comments = json.loads(p.read_text())
        for i, c in enumerate(comments):
            if c["id"] == comment_id:
                if c["wallet"].lower() != wallet.lower():
                    raise HTTPException(403, "Not your comment")
                comments.pop(i)
                p.write_text(json.dumps(comments, indent=2))
                return {"deleted": True}
    raise HTTPException(404, "Comment not found")
