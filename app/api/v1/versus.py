"""Versus endpoints — Firebase Firestore reads (read-only API).

L0 (public): leaderboard, athlete stats, matchup.
No write access — voting is frontend-only.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.trading import VersusAthlete, VersusMatchup

router = APIRouter(prefix="/versus", tags=["versus"])

# Firebase Firestore collections (same as Flutter frontend)
_COLLECTIONS = {
    "athletes": "athlete_elo_rankings",
    "rappers": "rapper_elo_rankings",
    "finance": "finance_bro_elo_rankings",
}


def _get_firestore():
    """Lazy-init Firestore client. Returns None if not configured."""
    try:
        import firebase_admin
        from firebase_admin import firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        return firestore.client()
    except Exception:
        return None


@router.get("/leaderboard", response_model=list[VersusAthlete])
async def get_leaderboard(
    category: str = Query("athletes", description="athletes | rappers | finance"),
    limit: int = Query(25, ge=1, le=100),
):
    """Top athletes by ELO, filterable by category."""
    db = _get_firestore()
    if db is None:
        return []

    collection = _COLLECTIONS.get(category, _COLLECTIONS["athletes"])
    docs = db.collection(collection).order_by("elo", direction="DESCENDING").limit(limit).stream()

    results = []
    for rank, doc in enumerate(docs, start=1):
        data = doc.to_dict()
        wins = data.get("wins", 0)
        losses = data.get("losses", 0)
        total = wins + losses
        results.append(VersusAthlete(
            athlete_id=doc.id,
            name=data.get("athleteName", doc.id),
            team=data.get("team", ""),
            category=category,
            elo=data.get("elo", 1500.0),
            wins=wins,
            losses=losses,
            record=f"{wins}-{losses}",
            win_pct=round(wins / total * 100, 1) if total > 0 else 0.0,
            rank=rank,
        ))
    return results


@router.get("/athlete/{athlete_id}", response_model=VersusAthlete)
async def get_athlete(
    athlete_id: str,
    category: str = Query("athletes"),
):
    """Single athlete stats."""
    db = _get_firestore()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore unavailable")

    collection = _COLLECTIONS.get(category, _COLLECTIONS["athletes"])
    doc = db.collection(collection).document(athlete_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Athlete not found")

    data = doc.to_dict()
    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    total = wins + losses
    return VersusAthlete(
        athlete_id=doc.id,
        name=data.get("athleteName", doc.id),
        team=data.get("team", ""),
        category=category,
        elo=data.get("elo", 1500.0),
        wins=wins,
        losses=losses,
        record=f"{wins}-{losses}",
        win_pct=round(wins / total * 100, 1) if total > 0 else 0.0,
    )


@router.get("/matchup", response_model=VersusMatchup)
async def get_matchup(
    category: str = Query("athletes"),
):
    """Get a random matchup pair for display purposes."""
    import random

    db = _get_firestore()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore unavailable")

    collection = _COLLECTIONS.get(category, _COLLECTIONS["athletes"])
    # Grab top 20 and pick 2 randomly for a fair matchup
    docs = list(db.collection(collection).order_by("elo", direction="DESCENDING").limit(20).stream())
    if len(docs) < 2:
        raise HTTPException(status_code=404, detail="Not enough athletes")

    a_doc, b_doc = random.sample(docs, 2)

    def _to_athlete(doc):
        data = doc.to_dict()
        w, l = data.get("wins", 0), data.get("losses", 0)
        t = w + l
        return VersusAthlete(
            athlete_id=doc.id,
            name=data.get("athleteName", doc.id),
            team=data.get("team", ""),
            category=category,
            elo=data.get("elo", 1500.0),
            wins=w, losses=l,
            record=f"{w}-{l}",
            win_pct=round(w / t * 100, 1) if t > 0 else 0.0,
        )

    return VersusMatchup(athlete_a=_to_athlete(a_doc), athlete_b=_to_athlete(b_doc))
