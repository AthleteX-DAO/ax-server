import asyncio
from fastapi.testclient import TestClient
from app.main import app
import sys

def test_api():
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/health")
        print("Health:", resp.status_code, resp.text)
        
        resp = client.get("/api/v1/oracle/0x066ef68c9d9ca51eee861aeb5bce51a12e61f06f10bf62243c563671ae3a9733")
        print("Oracle:", resp.status_code, resp.text)
        
        print("ax-server syntax is OK and endpoints are registered successfully.")
    except Exception as e:
        print("Error booting server:", e)
        sys.exit(1)

if __name__ == "__main__":
    test_api()
