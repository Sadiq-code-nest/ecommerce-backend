from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def home():
    return {"message": "My backend journey starts here"}


@app.get("/health")
def health():
    return {"status": "ok"}