import uvicorn
from fastapi import FastAPI
from .routes import router as media_router
from .config import PORT

app = FastAPI()
app.include_router(media_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
