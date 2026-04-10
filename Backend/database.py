import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_database = os.getenv("DB_NAME")
db_username = os.getenv("DB_USER")
db_pass = os.getenv("DB_PASSWORD")

def get_connection_string():
    return(
    psycopg2.connect(
    host = db_host,
    port = db_port,
    dbname = db_database,
    user = db_username,
    password = db_pass
)   
)
