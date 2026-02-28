from fastapi import FastAPI

app = FastAPI(title="RangeCrawler Dashboard")

@app.get("/")
async def root():
    return {"message": "Welcome to the RangeCrawler Dashboard"}

@app.get("/health")
async def health():
    return {"status": "ok"}
