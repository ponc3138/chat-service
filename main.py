from typing_extensions import Annotated
from fastapi import FastAPI, HTTPException, Depends
from database import check_db_health, create_user_db, get_user_db, get_user_by_id_db, create_room_db, join_room_db, get_room_by_id_db, get_user_rooms_db, create_message_db, get_room_and_membership_db
from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator
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

# makes sure a room name is not just white space. and returns name with all whitespace removed
def validate_room_name(name : str):
    if(len(name.strip()) < 1):
        raise ValueError(f"Room name cannot be blank")
    return name.strip()

class Room(BaseModel):
    room_name : Annotated[str, AfterValidator(validate_room_name)]

class MessageCreate(BaseModel):
    content : str = Field(max_length=2000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value : str) -> str:
        if(not value.strip()):
            raise ValueError("Message cannot be empty")
        return value

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


@app.post("/rooms", status_code=201)
def create_room(room : Room, _user : dict = Depends(get_current_user)):
    try:
        created_room = create_room_db(room.room_name)
        return created_room
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Room name already used")

@app.post("/rooms/{id}/join", status_code=201)
def join_room(id : int, user : dict = Depends(get_current_user)):
    try:
        join_room_db(user['id'], id)
        room = get_room_by_id_db(id)
        return {"message" : "Successfully joined room", 
                "room" : room
                }
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="User already in room")        
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(status_code=404, detail="Room does not exist")
    except psycopg.Error as e:
        print(f"error {e}")
        raise HTTPException(status_code=500, detail="Server error")

@app.get("/rooms")
def get_rooms(user : dict = Depends(get_current_user)):
    try: 
        rooms = get_user_rooms_db(user['id'])
        return {"rooms" : rooms}
    except psycopg.Error as e:
        print(e)
        raise HTTPException(status_code=500, detail="Server error")

@app.post("/rooms/{room_id}/messages")
def write_message(room_id : int, message : MessageCreate, user : dict = Depends(get_current_user)):
    try:
        room_info = get_room_and_membership_db(room_id, user['id'])

        if(room_info is None):
            raise HTTPException(status_code=404, detail="Room does not exist")
        if(not room_info['is_member']):
            raise HTTPException(status_code=403, detail="User not in room")
        
        message_info = create_message_db(user['id'], room_id, message.content)
        return message_info
    except psycopg.Error as e:
        print(e)
        raise HTTPException(status_code=500, detail="Server error")