from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import google.genai
from pydantic import BaseModel, Field
import json
from typing import Optional, Literal, List
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

load_dotenv(".env")

MONGODB_URL = os.getenv("MONGODB_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not MONGODB_URL:
    raise RuntimeError("MONGODB_URL missing in .env")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon/dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Mongo ----------------
mongo_client = AsyncIOMotorClient(MONGODB_URL)
db = mongo_client["website_customizer"]
layouts_col = db["layouts"]                 # current layout
versions_col = db["layout_versions"]        # last 4 snapshots


def to_oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid layoutId")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def snapshot_previous(layout_oid: ObjectId, innerHTML: str, reason: str):
    """Insert a snapshot, then keep only last 4 snapshots for that layout."""
    now = datetime.now(timezone.utc)

    await versions_col.insert_one({
        "layoutId": layout_oid,
        "innerHTML": innerHTML,
        "reason": reason,
        "createdAt": now
    })

    # delete snapshots beyond the newest 4
    cursor = versions_col.find({"layoutId": layout_oid}, {"_id": 1}).sort("createdAt", -1).skip(4)
    old_ids = [doc["_id"] async for doc in cursor]
    if old_ids:
        await versions_col.delete_many({"_id": {"$in": old_ids}})


@app.on_event("startup")
async def startup():
    await versions_col.create_index([("layoutId", 1), ("createdAt", -1)])


# ---------------- Models ----------------
Theme = Literal["Indigo", "Emerald", "Rose", "Cyan", "Amber", "Violet"]


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50_000)
    innerHTML: str = Field(..., min_length=1, max_length=1_000_000)


class CreateLayoutRequest(BaseModel):
    innerHTML: str = Field(..., min_length=1, max_length=1_000_000)
    theme: Optional[Theme] = None


class UpdateLayoutRequest(BaseModel):
    innerHTML: str = Field(..., min_length=1, max_length=1_000_000)
    reason: str = Field(default="manual_update", max_length=2000)
    theme: Optional[Theme] = None


class LayoutOut(BaseModel):
    layoutId: str
    innerHTML: str
    theme: Optional[str] = None
    updatedAt: str


class VersionOut(BaseModel):
    versionId: str
    createdAt: str
    reason: str


class VersionsOut(BaseModel):
    layoutId: str
    versions: List[VersionOut]


# ---------------- Routes ----------------
@app.get("/health")
async def health_check():
    try:
        await db.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False
    return {"ok": True, "mongo": mongo_ok}


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not found")

    try:
        gemini_prompt = f"""
You are an assistant helping edit a website layout.

You will output changes as an array of actions. Do NOT output HTML.

The frontend supports ONLY these action objects in the "changes" array:

1) Move a component:
{{ "type": "move", "component": "hero|featured-products|testimonials|newsletter|footer", "position": "top|bottom|<number>" }}

2) Remove a component:
{{ "type": "remove", "component": "hero|featured-products|testimonials|newsletter|footer" }}

3) Toggle visibility:
{{ "type": "toggle_visibility", "component": "hero|featured-products|testimonials|newsletter|footer", "visible": true|false }}

4) Update text content in a section:
{{ "type": "update_props", "component": "hero|featured-products|testimonials|newsletter|footer",
  "section": "<one of the provided section keys>", "props": {{ "<key>": "<string value>" }} }}

5) Update theme:
{{ "type": "update_theme", "theme": {{ "primaryColor": "indigo|emerald|rose|amber|cyan|violet",
  "spacing": "compact|comfortable", "mode": "light|dark" }} }}

IMPORTANT RULES:
- Return ONLY valid JSON, no markdown, no extra text.
- "changes" must be an array of action objects.
- Use only these components: hero, featured-products, testimonials, newsletter, footer.
- If you are unsure, return an empty changes array [] and explain in "reason".
- Keep the number of actions small (max 8).

Context (current HTML for reference only, do NOT output HTML):
{req.innerHTML}

User request:
{req.prompt}

Return ONLY this JSON format:
{{
  "reason": "one short paragraph",
  "changes": [ /* array of action objects */ ],
  "theme": {{
    "primaryColor": "indigo|emerald|rose|amber|cyan|violet",
    "spacing": "compact|comfortable",
    "mode": "light|dark"
  }}
}}
"""

        client = google.genai.Client(api_key=GEMINI_API_KEY)
        res = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=gemini_prompt
        )

        text = (res.text or "").strip()

        # Extract JSON object (Gemini sometimes adds extra text)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise HTTPException(status_code=500, detail="Gemini did not return JSON")

        data = json.loads(text[start:end+1])

        # Required fields
        if "reason" not in data or "changes" not in data:
            raise HTTPException(status_code=500, detail="Missing required fields in Gemini response")

        if not isinstance(data["reason"], str):
            raise HTTPException(status_code=500, detail="Field 'reason' must be a string")

        if not isinstance(data["changes"], list):
            raise HTTPException(status_code=500, detail="Field 'changes' must be an array")

        # Light validation: action type must be one of these
        allowed_types = {"move", "remove", "add", "update_props", "toggle_visibility", "update_theme"}
        for action in data["changes"]:
            if not isinstance(action, dict):
                raise HTTPException(status_code=500, detail="Each change must be an object")
            if action.get("type") not in allowed_types:
                raise HTTPException(status_code=500, detail=f"Invalid change type: {action.get('type')}")

        # Theme is optional in your TS type, but you usually want it present.
        # We'll allow missing theme, but if present validate it loosely.
        if "theme" in data and data["theme"] is not None:
            theme = data["theme"]
            if not isinstance(theme, dict):
                raise HTTPException(status_code=500, detail="Field 'theme' must be an object")
            if theme.get("primaryColor") not in ["indigo", "emerald", "rose", "amber", "cyan", "violet"]:
                raise HTTPException(status_code=400, detail="Invalid theme.primaryColor")
            if theme.get("spacing") not in ["compact", "comfortable"]:
                raise HTTPException(status_code=400, detail="Invalid theme.spacing")
            if theme.get("mode") not in ["light", "dark"]:
                raise HTTPException(status_code=400, detail="Invalid theme.mode")

        return data

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Gemini returned invalid JSON")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------- Layout persistence (NO AUTH, by layoutId) -----------

@app.post("/layouts", response_model=LayoutOut)
async def create_layout(req: CreateLayoutRequest):
    now = datetime.now(timezone.utc)
    doc = {
        "innerHTML": req.innerHTML,
        "theme": req.theme,
        "createdAt": now,
        "updatedAt": now
    }
    res = await layouts_col.insert_one(doc)
    layout_id = res.inserted_id

    # initial snapshot (so you can restore initial)
    await snapshot_previous(layout_id, req.innerHTML, "initial_create")

    return LayoutOut(
        layoutId=str(layout_id),
        innerHTML=req.innerHTML,
        theme=req.theme,
        updatedAt=iso(now)
    )


@app.get("/layouts/{layoutId}", response_model=LayoutOut)
async def get_layout(layoutId: str):
    oid = to_oid(layoutId)
    doc = await layouts_col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Layout not found")

    return LayoutOut(
        layoutId=layoutId,
        innerHTML=doc["innerHTML"],
        theme=doc.get("theme"),
        updatedAt=iso(doc["updatedAt"])
    )


@app.patch("/layouts/{layoutId}", response_model=LayoutOut)
async def update_layout(layoutId: str, req: UpdateLayoutRequest):
    oid = to_oid(layoutId)
    current = await layouts_col.find_one({"_id": oid})
    if not current:
        raise HTTPException(status_code=404, detail="Layout not found")

    # snapshot previous for undo
    await snapshot_previous(oid, current["innerHTML"], req.reason or "manual_update")

    now = datetime.now(timezone.utc)
    update_doc = {"innerHTML": req.innerHTML, "updatedAt": now}
    if req.theme is not None:
        update_doc["theme"] = req.theme

    await layouts_col.update_one({"_id": oid}, {"$set": update_doc})

    return LayoutOut(
        layoutId=layoutId,
        innerHTML=req.innerHTML,
        theme=req.theme if req.theme is not None else current.get("theme"),
        updatedAt=iso(now)
    )


@app.get("/layouts/{layoutId}/versions", response_model=VersionsOut)
async def get_versions(layoutId: str, limit: int = 4):
    if limit < 1 or limit > 10:
        raise HTTPException(status_code=400, detail="limit must be 1..10")

    oid = to_oid(layoutId)

    exists = await layouts_col.find_one({"_id": oid}, {"_id": 1})
    if not exists:
        raise HTTPException(status_code=404, detail="Layout not found")

    cursor = versions_col.find({"layoutId": oid}, {"innerHTML": 0}).sort("createdAt", -1).limit(limit)

    out = []
    async for v in cursor:
        out.append(VersionOut(
            versionId=str(v["_id"]),
            createdAt=iso(v["createdAt"]),
            reason=v.get("reason", "")
        ))

    return VersionsOut(layoutId=layoutId, versions=out)


@app.post("/layouts/{layoutId}/versions/{versionId}/restore", response_model=LayoutOut)
async def restore_version(layoutId: str, versionId: str):
    layout_oid = to_oid(layoutId)
    version_oid = to_oid(versionId)

    current = await layouts_col.find_one({"_id": layout_oid})
    if not current:
        raise HTTPException(status_code=404, detail="Layout not found")

    version = await versions_col.find_one({"_id": version_oid, "layoutId": layout_oid})
    if not version:
        raise HTTPException(status_code=404, detail="Version not found for this layout")

    # snapshot current before restoring (so restore itself is undoable)
    await snapshot_previous(layout_oid, current["innerHTML"], "restore_snapshot")

    now = datetime.now(timezone.utc)
    await layouts_col.update_one(
        {"_id": layout_oid},
        {"$set": {"innerHTML": version["innerHTML"], "updatedAt": now}}
    )

    return LayoutOut(
        layoutId=layoutId,
        innerHTML=version["innerHTML"],
        theme=current.get("theme"),
        updatedAt=iso(now)
    )
