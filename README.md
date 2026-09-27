# KIFACH

Turn one expert demonstration into a reviewable procedure, then assess a learner's attempt with evidence.

## Run

### Backend

From the repository root, create and activate a Python virtual environment:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`, then use the same install and run commands. The FastAPI development server listens on `http://127.0.0.1:8000`; open `http://127.0.0.1:8000/health` to check it, and press Ctrl+C to stop it. Only the health endpoint works so far; the teach, review, and practice APIs are still stubs.

### Frontend

In a second terminal, start the blank React shell:

```sh
cd frontend
npm install
npm run dev
```

Start with [the documentation index](docs/README.md), including the [five-person work split](docs/team-plan.md).
