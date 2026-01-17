from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import google.genai
from pydantic import BaseModel

load_dotenv(".env")

app = FastAPI()

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

class Prompt(BaseModel):
	prompt: str
	
# Placeholder
@app.post("/chat")
def chat_endpoint(prompt: Prompt):
	api_key = os.getenv("GEMINI_API_KEY")
	if not api_key:
		raise HTTPException(status_code=500, detail="Gemini API key not found")
	try:
		client = google.genai.Client(api_key=api_key)
		res = client.models.generate_content(
			model="gemini-2.5-flash",
			contents=f"Given the prompt \"{prompt}\", determine if it's a country or not. If it's a country, then state its capital"
		)
		return {"response": res.text}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))