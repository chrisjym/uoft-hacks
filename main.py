from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import google.genai
from pydantic import BaseModel, Field
import json

load_dotenv(".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50_000)
    innerHTML: str = Field(..., min_length=1, max_length=1_000_000)
	
@app.get("/health")
def health_check():
     return {"response": "All good!"}

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not found")

    try:
        gemini_prompt = f"""
You are a web designer.

Current innerHTML:
{req.innerHTML}

User request:
{req.prompt}

Return ONLY valid JSON (no markdown, no extra text) in this exact format:
{{
  "reason": "one short paragraph explaining what you changed",
  "changes": "the full modified innerHTML string",
  "theme": "Indigo"
}}
Where theme must be one of: Indigo, Emerald, Rose, Cyan, Amber, Violet.
"""

        client = google.genai.Client(api_key=GEMINI_API_KEY)
        res = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=gemini_prompt
        )

        text = (res.text or "").strip()

        # Try to parse JSON safely (Gemini sometimes adds text)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise HTTPException(status_code=500, detail="Gemini did not return JSON")

        data = json.loads(text[start:end+1])

        # Validate required fields exist
        for k in ("reason", "changes", "theme"):
            if k not in data:
                raise HTTPException(status_code=500, detail=f"Missing field in Gemini response: {k}")

        if data["theme"] not in ["Indigo", "Emerald", "Rose", "Cyan", "Amber", "Violet"]:
            raise HTTPException(status_code=400, detail="Invalid theme returned by Gemini")

        if len(data["changes"]) > 1_000_000:
            raise HTTPException(status_code=400, detail="AI output too large")

        return data

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Gemini returned invalid JSON")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
	
class LayoutResponse(BaseModel):
	innerHTML: str

@app.patch("/update-layout")
def update_layout(response: LayoutResponse):
	layout: dict = response.model_dump()
	# Store layout in database
	return {"response": "Updated successfully"}

@app.get("/get-saved-layout/{layout_no}")
def get_saved_layout(layout_no: int):
	'''0 = newest, 3 - oldest'''
	if layout_no < 0 or layout_no > 3:
		raise HTTPException(status_code=500, detail='Inaccessible index')
	# Get the layout (as innerHTML)
	# if unable to get layout:
	#	raise HTTPException(status_code=501, detail='No layouts have been stored in this database.')
	# return {"response": layout_innerHTML}

@app.post("/create-new-layout")
def create_new_layout(response: LayoutResponse):
	# TEST: If any layouts have been stored, if there exists one:
	# 	raise HTTPException(status_code=500, detail='Unable to create a new layout as there already exists one in the database.')
	
	layout: dict = response.model_dump()
	# Store layout in database
	return {"response": "Created successfully"}
