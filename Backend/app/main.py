from fastapi import FastAPI

app = FastAPI(title="SKILL PROOF API")

@app.get("/")
async def welcome():
    return {"message" : "Welcome to Skill Proof AI"}



