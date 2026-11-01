"""Evidence Rescue Radar APIs: ranked recommendations and human actions only."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.rescue.missing_evidence import rank_evidence_needs
from services.api.auth.session import current_user
from services.api.db.models import Case, DynamicsRun, EvidenceNeed, ReviewerAction, SourceMedia
from services.api.db.session import get_db

router = APIRouter(prefix="/cases/{case_id}/evidence-needs", tags=["evidence-rescue"])
ALLOWED_STATES = {"verified_source", "drafted", "requested_by_user", "received", "unavailable", "refused"}


class NeedAction(BaseModel):
    state: str = Field(..., pattern="^(verified_source|drafted|requested_by_user|received|unavailable|refused)$")
    source_description: str | None = Field(None, max_length=500)
    verified: bool = False
    retention_deadline: datetime | None = None
    timezone_name: str | None = Field(None, max_length=80)
    contact_name: str | None = Field(None, max_length=200)
    contact_details: str | None = Field(None, max_length=500)


class DraftRequest(BaseModel):
    recipient: str = Field(..., min_length=1, max_length=200)
    source_description: str = Field(..., min_length=3, max_length=500)
    date_range: str = Field(..., min_length=3, max_length=120)
    time_range: str = Field(..., min_length=3, max_length=120)


@router.get("")
async def list_needs(case_id: str, db: AsyncSession = Depends(get_db),
                     _: str = Depends(current_user)) -> dict:
    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    runs = (await db.execute(select(DynamicsRun).where(
        DynamicsRun.case_id == case_id, DynamicsRun.status == "done"
    ).order_by(DynamicsRun.created_at.desc()))).scalars().all()
    certificates = json.loads(runs[0].certificates_json or "{}") if runs else {
        "entry_speed": {"status": "not_identifiable", "limiting_source": "scale_calibration"}}
    media = (await db.execute(select(SourceMedia).where(SourceMedia.case_id == case_id))).scalars().all()
    existing = (await db.execute(select(EvidenceNeed).where(EvidenceNeed.case_id == case_id))).scalars().all()
    by_key = {row.need_key: row for row in existing}
    known_sources, deadlines = [], {}
    now = datetime.now(timezone.utc)
    for row in existing:
        detail = json.loads(row.verification_json or "{}")
        if detail.get("verified") and detail.get("source_description"):
            known_sources.append({"need_key": row.need_key, "verified": True})
        deadline_value = detail.get("retention_deadline")
        if detail.get("verified") and deadline_value:
            deadline = datetime.fromisoformat(deadline_value)
            if deadline.tzinfo is not None:
                deadlines[row.need_key] = max(0.0, (deadline - now).total_seconds() / 3600.0)
    suggestions = rank_evidence_needs(certificates, known_sources=known_sources, verified_deadlines=deadlines)
    for suggestion in suggestions:
        row = by_key.get(suggestion["need_key"])
        if row:
            suggestion.update({"id": row.id, "state": row.state,
                               "verification": json.loads(row.verification_json) if row.verification_json else None,
                               "draft_text": row.draft_text})
            continue
        row = EvidenceNeed(id=str(uuid.uuid4()), case_id=case_id, need_key=suggestion["need_key"],
                           snapshot_json=json.dumps(suggestion, sort_keys=True), state="suggested",
                           created_by="system", updated_by="system")
        db.add(row)
        suggestion.update({"id": row.id, "state": row.state, "verification": None, "draft_text": None})
    await db.commit()
    return {"case_id": case_id, "analysis_run_id": runs[0].id if runs else None,
            "media_count": len(media), "needs": suggestions,
            "retention_deadline_default": "unknown", "ranking_note": "Heuristic ranking, not a probability; no source or owner is inferred."}


@router.post("/{need_id}/verification")
async def update_need(case_id: str, need_id: str, payload: NeedAction,
                      db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    row = await db.get(EvidenceNeed, need_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(404, "Evidence need not found")
    if payload.state in {"verified_source", "requested_by_user", "received"} and not payload.verified:
        raise HTTPException(422, "This state requires explicit human verification")
    if payload.state == "verified_source" and not payload.source_description:
        raise HTTPException(422, "Describe the human-verified source")
    if payload.retention_deadline and (not payload.verified or not payload.timezone_name):
        raise HTTPException(422, "A deadline requires human verification and a timezone")
    details = payload.model_dump(mode="json")
    if payload.retention_deadline and payload.retention_deadline.tzinfo is None:
        raise HTTPException(422, "Retention deadline must include a timezone offset")
    previous_state = row.state
    row.state = payload.state
    row.verification_json = json.dumps(details, sort_keys=True)
    row.updated_by = user
    db.add(ReviewerAction(id=str(uuid.uuid4()), case_id=case_id, target_type="evidence_need",
                          target_id=row.id, action="update_state", before_json=json.dumps({"state": previous_state}),
                          after_json=json.dumps({"state": payload.state, "verification": details}, sort_keys=True),
                          actor=user))
    await db.commit()
    return {"id": row.id, "state": row.state, "verification": details,
            "updated_by": user, "updated_at": datetime.now(timezone.utc).isoformat()}


@router.post("/{need_id}/draft")
async def draft_request(case_id: str, need_id: str, payload: DraftRequest,
                        db: AsyncSession = Depends(get_db), user: str = Depends(current_user)) -> dict:
    row = await db.get(EvidenceNeed, need_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(404, "Evidence need not found")
    verification = json.loads(row.verification_json or "{}")
    if verification.get("verified") is not True:
        raise HTTPException(409, "Verify the source with a person before drafting a request")
    text = (f"To: {payload.recipient}\n\nPlease preserve any relevant original video or records for "
            f"{payload.source_description}, covering {payload.date_range}, {payload.time_range}. "
            "Please retain the original export and associated time metadata if available. "
            "This is a draft for human review; it has not been sent.\n")
    row.draft_text = text
    row.state = "drafted"
    row.updated_by = user
    db.add(ReviewerAction(id=str(uuid.uuid4()), case_id=case_id, target_type="evidence_need",
                          target_id=row.id, action="create_unsent_draft",
                          after_json=json.dumps({"draft_sha256": __import__("hashlib").sha256(text.encode()).hexdigest(), "sent": False}),
                          actor=user))
    await db.commit()
    return {"id": row.id, "state": row.state, "draft": text, "sent": False,
            "created_by": user, "created_at": datetime.now(timezone.utc).isoformat()}
