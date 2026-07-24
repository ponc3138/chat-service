from fastapi import FastAPI, HTTPException, Depends
from database import check_db_health, create_user_db, get_user_db, get_user_by_id_db
from pydantic import BaseModel, EmailStr
from pwdlib import PasswordHash
import psycopg
import jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv


app = FastAPI()

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")
password_hash = PasswordHash.recommended()

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserPublic(BaseModel):
    id : int
    email : EmailStr
    username : str

def create_token(user_id):
    # token expects a 'sub' wich is the subject, or the user (can be email, username, user id...), 
    # and 'exp' which is the expiration of the token
    payload = {
        # 'sub' needs to be converted to string if not one
        "sub" : str(user_id),
        "exp" : datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    # creates the token using the payload, key, and algorithm
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token

def decode_token(token):
    # decodes the token to make sure its valid
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # if token is valid, it returns the payload
        return payload
    # Expired token
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Expired token")
    # Token is not valid
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid Token")

def get_current_user(token : str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    user_id = int(payload['sub'])
    user = get_user_by_id_db(user_id)
    if(user is None):
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return user

@app.get("/health")
def get_health():
    if(not check_db_health()):
        return {"status" : "unhealthy",
                "database" : "error"}
    else:
        return {"status" : "healthy",
                "database": "connected"}
    
@app.post("/users", status_code=201)
def create_user(user: UserCreate):
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


@app.post("/login")
def login(form_data : OAuth2PasswordRequestForm = Depends()):
    # Fetch user by email or uersname. says '.username' because that's the field in the request form
    logged_user = get_user_db(form_data.username)
    if(logged_user is None):
        # Returns unauthorized if the email or userame does not exist
        raise HTTPException(status_code=401, detail="Invalid email, username, or password")
    
    # Verifies the plain password against the stored hash
    if(password_hash.verify(form_data.password, logged_user['hashed_password'])):
        # creates token for user, and returns it
        token = create_token(logged_user['id'])
        return {"access_token" : token, "token_type": "bearer"}
    else: 
        # Returns unauthorized if the password is incorrect
        raise HTTPException(status_code=401, detail="Invalid email, username, or password")


@app.get("/me", response_model=UserPublic)
def get_me(user : dict = Depends(get_current_user)):
    # gets user information from get_current_user, and returns it 
    return user
