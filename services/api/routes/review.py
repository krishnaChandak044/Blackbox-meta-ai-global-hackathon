"""Review actions router stub — Phase 2+."""
from fastapi import APIRouter
router = APIRouter(prefix="/cases/{case_id}/review", tags=["review"])
