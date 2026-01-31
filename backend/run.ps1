# Run DJMashAI backend (no need to activate venv)
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
