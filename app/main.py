from fastapi import FastAPI
import uvicorn

from .config import PORT
from .routes import router as media_router


app = FastAPI()
app.include_router(media_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
