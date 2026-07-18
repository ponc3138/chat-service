from fastapi import FastAPI, HTTPException
from database import check_db_health, create_user_db
from pydantic import BaseModel, EmailStr
from pwdlib import PasswordHash
import psycopg

app = FastAPI()

password_hash = PasswordHash.recommended()

class User(BaseModel):
    username: str
    email: EmailStr
    password: str

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
    
@app.post("/users", status_code=201)
def create_user(user: User):
    # hash password
    hashed_password = password_hash.hash(user.password)
    try:
        # try creating new user
        create_user_db(user.username, user.email, hashed_password)
        success_message = f"user '{user.username}' created"
        return {"success" : success_message}
    # store error in variable 'e'
    except psycopg.errors.UniqueViolation as e:
        # check what column is causing UniqueViolation error
        if(e.diag.constraint_name == 'users_username_key'):
            raise HTTPException(status_code=409, detail="Username already in use")
        elif(e.diag.constraint_name == 'users_email_key'):
            raise HTTPException(status_code=409, detail="Email already in use")
        else: 
            # for unexpected UniqueViolation erros
            print(e)
            raise HTTPException(status_code=500, detail="Unexpected error")
    # catch all for database errors
    except psycopg.DatabaseError as e:
        print(e)
        raise HTTPException(status_code=500, detail="Unexpected error")
