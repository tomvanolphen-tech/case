from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from web.routers import inbox, pipeline, review, rules

app = FastAPI(title="Factuurverwerking")

BASE = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

app.include_router(inbox.router,    prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(review.router,   prefix="/api")
app.include_router(rules.router,    prefix="/api")


@app.get("/")
async def root():
    return RedirectResponse("/static/pages/index.html")


if __name__ == "__main__":
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
