import requests
import json

API_KEY = "b6d9d5cade6889d054b9dbae9fbe2be05bea1511d9431f2aaa4db627d148c305"

params = {
    "engine": "google_maps",   # or "google"
    "q": "buddhist temple sri lanka",
    "api_key": API_KEY
}

response = requests.get("https://serpapi.com/search.json", params=params)
data = response.json()

with open("results.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("Saved results.json")