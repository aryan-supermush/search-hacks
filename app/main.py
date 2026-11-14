from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .core import ROOT
from .plan import plan
from .routes import TZ

app = FastAPI(title="Stride")


class PlanRequest(BaseModel):
    origin: str
    destination: str
    end_time: str  # "2026-11-14T19:00" local time
    max_extra_minutes: int = 10


@app.post("/api/plan")
def api_plan(req: PlanRequest):
    try:
        end = datetime.fromisoformat(req.end_time).replace(tzinfo=TZ)
        return plan(req.origin, req.destination, end, req.max_extra_minutes)
    except KeyError as e:
        raise HTTPException(500, f"Missing environment variable {e}")
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html", headers={"Cache-Control": "no-store"})
