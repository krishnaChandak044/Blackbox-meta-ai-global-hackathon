"""Exports router stub — Phase 5."""
from fastapi import APIRouter
router = APIRouter(prefix="/cases/{case_id}/exports", tags=["exports"])
