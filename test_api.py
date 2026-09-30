import requests
import json

url = "http://localhost:5000/generate"

payload = {
    "query": "Show current weather with temperature, humidity and a 5-day forecast",
    "response": (
        "Temperature: 18 C. "
        "Humidity: 70 percent. "
        "Today 18 C/9 C. "
        "Tomorrow 22 C/13 C. "
        "Thursday 19 C/7 C. "
        "Friday 23 C/14 C."
    )
}

print("Sending request to:", url)
print("Please wait...")

response = requests.post(
    url,
    json=payload,
    timeout=300
)

print()
print("HTTP STATUS:", response.status_code)
print()
print(response.text)