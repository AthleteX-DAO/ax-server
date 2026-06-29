import httpx
try:
    r = httpx.get("http://localhost:8000/api/v1/predict/markets/25")
    print("API RESPONSE:", r.json())
except Exception as e:
    print(e)
