import psycopg
from psycopg_pool import ConnectionPool
import os
from dotenv import load_dotenv
from psycopg.rows import dict_row


load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if(not DATABASE_URL):
    print("Missing DATABASE_URL")
    exit()

pool = ConnectionPool(DATABASE_URL, open=True)

def check_db_health():
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except psycopg.DatabaseError: 
        return False
    

def create_user_db(username, email, hashed_password):
    with pool.connection() as conn:
        with conn.cursor() as cur: 
            # Store usernames and emails in lowercase for consistency and uniqueness
            cur.execute("""INSERT INTO users (username, email, hashed_password)
                        VALUES (%s, %s, %s)""", (username.strip().lower(), email.strip().lower(), hashed_password))
        
def get_user_db(identifier):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # searches user by username and email
            result = cur.execute(""" SELECT *
                        FROM users
                        WHERE LOWER(email) = LOWER(%s)
                        OR LOWER(username) = LOWER(%s) """, (identifier.strip(), identifier.strip()))
            return result.fetchone()


def get_user_by_id_db(user_id):
     with pool.connection() as conn:
         with conn.cursor(row_factory=dict_row) as cur:
             result = cur.execute(""" SELECT id, email, username
                                  FROM users
                                  WHERE id = (%s) """, (user_id, ))
             return result.fetchone()

def create_room_db(room_name):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur: 
            result = cur.execute("""INSERT INTO rooms (room_name)
                        VALUES (%s)
                        RETURNING id, room_name""", (room_name.strip(), ))
            return result.fetchone()
        
def join_room_db(user_id, room_id):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            result = cur.execute(""" INSERT INTO room_users (user_id, room_id)
                        VALUES (%s, %s) 
                        RETURNING user_id, room_id""", (user_id, room_id))
            return result.fetchone()
        
def get_room_by_id_db(id):
     with pool.connection() as conn:
         with conn.cursor(row_factory=dict_row) as cur:
             result = cur.execute(""" SELECT *
                                  FROM rooms
                                  WHERE id = (%s) """, (id, ))
             return result.fetchone()

def get_user_rooms_db(user_id):
     with pool.connection() as conn:
         with conn.cursor(row_factory=dict_row) as cur:
             result = cur.execute(""" SELECT room_users.room_id, rooms.room_name
                                  FROM room_users
                                  INNER JOIN rooms on room_users.room_id = rooms.id
                                  WHERE room_users.user_id = (%s) """, (user_id, ))
             return result.fetchall()

def create_message_db(user_id, room_id, content):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            result = cur.execute(""" INSERT INTO messages (user_id, room_id, content)
                VALUES (%s, %s, %s)
                RETURNING user_id, room_id, content""", (user_id, room_id, content))
            return result.fetchone()

def get_room_and_membership_db(room_id, user_id):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Return the room if it exists, along with whether the given user
            # is a member of that room. 
            result = cur.execute(""" SELECT rooms.id AS room_id, rooms.room_name,
                (room_users.user_id IS NOT NULL) AS is_member
                FROM rooms
                -- LEFT JOIN keeps the room in the result even if the user
                -- has not joined it, allowing us to distinguish between
                -- "room doesn't exist" and "user isn't a member".
                LEFT JOIN room_users ON room_users.room_id = rooms.id and room_users.user_id = %s
                WHERE rooms.id = %s """, (user_id, room_id))
            return result.fetchone()