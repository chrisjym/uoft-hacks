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
def chat_endpoint(user_prompt: Prompt):
	api_key = os.getenv("GEMINI_API_KEY")
	if not api_key:
		raise HTTPException(status_code=500, detail="Gemini API key not found")
	if len(user_prompt.prompt) > 1048576:
		raise HTTPException(status_code=500, detail="Your message is too long")
	try:
		gemini_prompt = \
		f'''
		You are a web designer and you are given the innerHTML of a website as well as the user's prompt to modify
		the innerHTML such that it fits their criteria.

		The user prompt is {user_prompt}.

		Without further elaboration, return ONLY a JSON response as follows afterwards (such that it's under 65,536 tokens in total):
		{{
			"reason": <Insert your reasons for changing in a paragraph>,
			"changes": <Insert the modified innerHTML>,
			"theme": <any of "Indigo", "Emerald", "Rose", "Cyan", "Amber", "Violet">
		}}
		'''
		client = google.genai.Client(api_key=api_key)
		res = client.models.generate_content(
			model="gemini-3-pro-preview",
			contents=gemini_prompt
		)
		return {"response": res.text}
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