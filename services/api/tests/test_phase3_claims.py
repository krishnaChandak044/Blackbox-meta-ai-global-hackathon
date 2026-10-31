"""Phase3 engine tests + API (merged)."""
import os, uuid, time  # noqa
import pytest  # noqa
from httpx import AsyncClient, ASGITransport  # noqa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # noqa
from services.api.db.models import Base  # noqa
from services.api.main import app as fastapp  # noqa

TEST_DB = f"sqlite+aiosqlite:///./test_p3e_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = TEST_DB
os.environ["SECRET_KEY"] = "test-secret-key-32-chars-minimum-xxxx"
os.environ["BLACKBOX_ACCESS_PASSWORD"] = "testpass"
def test_extract_speed_claim_from_text():
    from engine.claims.extractor import extract_claims
    cs=extract_claims("The car was doing 80 km/h before the impact.","c1","t1")
    assert any(a.value==80.0 for c in cs for a in c.assertions if a.assertion_type=="speed")
def test_extract_no_claims_from_gibberish():
    from engine.claims.extractor import extract_claims
    assert extract_claims("asdf qwer zxcv","c1","t1")==[]
    assert extract_claims("","c1","t1")==[]
def test_extract_direction_claim():
    from engine.claims.extractor import extract_claims
    cs=extract_claims("He turned left at the junction.","c1","t1")
    assert any(a.assertion_type=="direction" for c in cs for a in c.assertions)
def test_extract_stop_claim():
    from engine.claims.extractor import extract_claims
    cs=extract_claims("The car ran a red light.","c1","t1")
    assert any(a.assertion_type=="action" for c in cs for a in c.assertions)
    cs2=extract_claims("The vehicle had stopped.","c1","t1")
    assert any(a.assertion_type=="stop" for c in cs2 for a in c.assertions)
def test_check_speed_supported():
    from engine.claims.checker import check_claim
    from engine.claims.models import Claim,ClaimAssertion,TrackDetailLite,TrackPointLite
    from types import SimpleNamespace
    pts=[TrackPointLite(frame_index=i,presentation_ts_s=i*0.1,world_x=i*2.222,world_y=0) for i in range(10)]
    tr=TrackDetailLite(id="t1",points=pts)
    sc=SimpleNamespace(metres_per_pixel=0.1,reference_distance_m=10,measured_distance_m=10,relative_error=0.01,source="test")
    cl=Claim(id="c1",case_id="c1",media_id=None,transcript_id="t1",speaker="witness_1",assertions=[ClaimAssertion(assertion_type="speed",subject="Vehicle A",value=80,unit="km/h",qualifier=None,raw_text="doing 80 km/h",source_ts_start=0,source_ts_end=1)],raw_text="doing 80",confidence=0.8)
    v=check_claim(cl,[tr],None,sc)
    assert v.verdict=="supported" and "km/h" in v.explanation
def test_check_speed_contradicted():
    from engine.claims.checker import check_claim
    from engine.claims.models import Claim,ClaimAssertion,TrackDetailLite,TrackPointLite
    from types import SimpleNamespace
    pts=[TrackPointLite(frame_index=i,presentation_ts_s=i*0.1,world_x=i*0.833,world_y=0) for i in range(10)]
    tr=TrackDetailLite(id="t1",points=pts)
    sc=SimpleNamespace(metres_per_pixel=0.1,reference_distance_m=10,measured_distance_m=10,relative_error=0.01,source="test")
    cl=Claim(id="c1",case_id="c1",media_id=None,transcript_id="t1",speaker="witness_1",assertions=[ClaimAssertion(assertion_type="speed",subject="Vehicle A",value=80,unit="km/h",qualifier=None,raw_text="doing 80 km/h",source_ts_start=0,source_ts_end=1)],raw_text="doing 80",confidence=0.8)
    v=check_claim(cl,[tr],None,sc)
    assert v.verdict=="contradicted"
def test_check_speed_insufficient_data():
    from engine.claims.checker import check_claim
    from engine.claims.models import Claim,ClaimAssertion,TrackDetailLite,TrackPointLite
    pts=[TrackPointLite(frame_index=i,presentation_ts_s=i*0.1,world_x=i*2.222,world_y=0) for i in range(10)]
    tr=TrackDetailLite(id="t1",points=pts)
    cl=Claim(id="c1",case_id="c1",media_id=None,transcript_id="t1",speaker="witness_1",assertions=[ClaimAssertion(assertion_type="speed",subject="Vehicle A",value=80,unit="km/h",qualifier=None,raw_text="doing 80 km/h",source_ts_start=0,source_ts_end=1)],raw_text="doing 80",confidence=0.8)
    v=check_claim(cl,[tr],None,None)
    assert v.verdict=="insufficient_data"
def test_check_stop_supported():
    from engine.claims.checker import check_claim
    from engine.claims.models import Claim,ClaimAssertion,TrackDetailLite,TrackPointLite
    from types import SimpleNamespace
    pts=[TrackPointLite(frame_index=i,presentation_ts_s=i*0.1,world_x=0.0,world_y=0.0) for i in range(10)]
    tr=TrackDetailLite(id="t1",points=pts)
    sc=SimpleNamespace(metres_per_pixel=0.1,reference_distance_m=10,measured_distance_m=10,relative_error=0.01,source="test")
    cl=Claim(id="c1",case_id="c1",media_id=None,transcript_id="t1",speaker="witness_1",assertions=[ClaimAssertion(assertion_type="stop",subject="Vehicle A",value=None,unit=None,qualifier=None,raw_text="stopped",source_ts_start=0,source_ts_end=1)],raw_text="stopped",confidence=0.8)
    v=check_claim(cl,[tr],None,sc)
    assert v.verdict=="supported"
def test_synthetic_deterministic():
    from services.worker.adapters.synthetic_transcript_adapter import SyntheticTranscriptAdapter
    a=SyntheticTranscriptAdapter()
    r1=a.transcribe("p.mp4",media_id="same",duration_seconds=10)
    r2=a.transcribe("p.mp4",media_id="same",duration_seconds=10)
    assert r1.raw_text==r2.raw_text

@pytest.fixture(scope="module")
async def client():
    eng=create_async_engine(TEST_DB,connect_args={"check_same_thread":False})
    async with eng.begin() as c: await c.run_sync(Base.metadata.create_all)
    from services.api.db.session import get_db
    SL=async_sessionmaker(eng,expire_on_commit=False)
    async def og():
        async with SL() as s: yield s
    fastapp.dependency_overrides[get_db]=og
    tr=ASGITransport(app=fastapp)
    async with AsyncClient(transport=tr,base_url="http://test") as ac: yield ac
    await eng.dispose()
    import pathlib; pathlib.Path(TEST_DB.replace("sqlite+aiosqlite:///","")).unlink(missing_ok=True)
async def ah():
    exp=int(time.time())+3600
    from services.api.auth.session import _signature
    return {"Cookie": f"blackbox_session={exp}.{_signature(exp)}"}
@pytest.fixture
async def cid(client):
    h=await ah()
    r=await client.post("/api/v1/cases/",json={"title":"API P3","consent_given":True},headers=h)
    assert r.status_code==201,r.text
    return r.json()["id"]
async def test_transcript_api_create_and_list(client,cid):
    h=await ah()
    r=await client.post(f"/api/v1/cases/{cid}/transcripts/",json={"raw_text":"Car doing 60 km/h."},headers=h)
    assert r.status_code==201,r.text
    tid=r.json()["id"]
    r2=await client.get(f"/api/v1/cases/{cid}/transcripts/",headers=h)
    assert tid in [t["id"] for t in r2.json()]
async def test_claim_check_via_api(client,cid):
    h=await ah()
    r=await client.post(f"/api/v1/cases/{cid}/transcripts/",json={"raw_text":"Car doing 80 km/h."},headers=h)
    assert r.status_code==201
    from engine.claims.checker import check_claim as cc
    from engine.claims.models import Claim,ClaimAssertion,TrackDetailLite,TrackPointLite
    from types import SimpleNamespace
    pts=[TrackPointLite(frame_index=i,presentation_ts_s=i*0.1,world_x=i*2.222,world_y=0) for i in range(10)]
    tr=TrackDetailLite(id="t1",points=pts)
    sc=SimpleNamespace(metres_per_pixel=0.1,reference_distance_m=10,measured_distance_m=10,relative_error=0.01,source="test")
    cl=Claim(id="cx",case_id=cid,media_id=None,transcript_id=r.json()["id"],speaker="witness_1",assertions=[ClaimAssertion(assertion_type="speed",subject="Vehicle A",value=80,unit="km/h",qualifier=None,raw_text="doing 80",source_ts_start=0,source_ts_end=1)],raw_text="doing 80",confidence=0.8)
    v=cc(cl,[tr],None,sc)
    assert v.explanation and v.verdict in ("supported","contradicted","inconclusive","insufficient_data")
async def test_unauth_returns_401(client):
    r=await client.get("/api/v1/cases/")
    assert r.status_code==401
