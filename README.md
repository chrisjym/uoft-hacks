Create a Python virtual environment! (.venv) & activate the environment.

Create a .env file to store GEMINI_API_KEY.

pip install "fastapi[standard]"

pip install python-dotenv

pip install -q -U google-genai

python -m pip install "pymongo[srv]"

Run command: uv run uvicorn main:app --reload
