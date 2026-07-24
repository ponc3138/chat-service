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