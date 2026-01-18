1. Create a Python virtual environment (.venv) & activate the environment.
2. Create a .env file to store your GEMINI_API_KEY (get one through Google AI Studio)
3. Install the following packages/librairies through the terminal:

- `pip install "fastapi[standard]"`
- `pip install uv`
- `pip install python-dotenv`
- `pip install -q -U google-genai`
- `python -m pip install "pymongo[srv]"`
- `python -m pip install motor`

4. Connect to a MongoDB database.
5. Run command: `uv run uvicorn main:app --reload`
