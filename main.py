from fastapi import FastAPI
from database import check_db_health
app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello World"}


@app.get("/health")
def get_health():
    if(not check_db_health()):
        return {"status" : "unhealthy",
                "database" : "error"}
    else:
        return {"status" : "healthy",
                "database": "connected"}
