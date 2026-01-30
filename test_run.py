import sys
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

try:
    import flask
    print(f"Flask version: {flask.__version__}")
except ImportError as e:
    print(f"Flask not installed: {e}")

try:
    import psycopg2
    print("psycopg2 is installed")
except ImportError as e:
    print(f"psycopg2 not installed: {e}")

try:
    from dotenv import load_dotenv
    import os
    load_dotenv(override=True)
    db_url = os.getenv("DATABASE_URL")
    print(f"DATABASE_URL: {db_url}")
except Exception as e:
    print(f"Error loading .env: {e}")
