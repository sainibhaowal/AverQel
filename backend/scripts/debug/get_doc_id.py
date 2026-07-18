import json
import sys
import urllib.request

req = urllib.request.Request(
    "http://localhost:1000/api/v1/documents",
    headers={
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMTljYWVkOS1hZTdhLTdjYzYtODkyMi01MWJlM2MyMzFlNDAiLCJ0ZW5hbnRfaWQiOiIwMTljYWVkOS1hZTNlLTczMzUtOTk2MS01NTIwMWUxYTQ5NDEiLCJyb2xlcyI6WyJhZG1pbiJdLCJqdGkiOiIyN2FhYzRmZS1kOGU0LTRiNzYtOWM5MC1hNTdhMWQ2MmM5MjkiLCJpYXQiOjE3NzI0ODQ4MjgsImV4cCI6MTc3MjQ4ODQyOCwiaXNzIjoiYWkta25vd2xlZGdlLXNlcnZpY2UiLCJhdWQiOiJhaS1rbm93bGVkZ2Utc2VydmljZS1hcGkifQ.Cm4FuuBbskhkSfwMNSBz9kdksGe5jYoDIe6fTQUKGx0",
        "X-Tenant-Id": "019caed9-ae3e-7335-9961-55201e1a4941",
    },
)

with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    for d in data["items"]:
        if d["filename"] == "2312.00752v2.pdf":
            print(d.get("id") or d.get("document_id"))
            sys.exit(0)
print("Not found", data["items"][0].keys() if data["items"] else "Empty")
