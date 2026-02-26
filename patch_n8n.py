import json
import os

filepath = "n8n-workflows/telegram_chatops.json"
if not os.path.exists(filepath):
    print("File not found")
    exit(1)

with open(filepath, "r") as f:
    data = json.load(f)

# Add Code node
code_node = {
  "parameters": {
    "jsCode": "const item = $input.first();\nif (item.json.body.error) {\n  return item;\n}\nitem.binary = {\n  data: {\n    data: item.json.body.image_base64,\n    mimeType: 'image/png',\n    fileName: 'image.png'\n  }\n};\nreturn item;"
  },
  "id": "base64-to-binary",
  "name": "Parse Base64",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [420, 400]
}

# Check if already added
has_code_node = False
for node in data["nodes"]:
    if node["name"] == "Parse Base64":
        has_code_node = True
        break
if not has_code_node:
    data["nodes"].append(code_node)

for node in data["nodes"]:
    if node["name"] == "Send Final Image":
        node["position"] = [640, 400]
        node["parameters"] = {
            "chatId": "={{ $json.body.chat_id }}",
            "operation": "sendPhoto",
            "file": "data",
            "caption": "=✅ [AI Media Factory] 작업 완료\n\nTask ID: {{$json.body.task_id}}\nPrompt: {{$json.body.prompt}}{{ $json.body.error ? '\\n\\n❌ 에러: ' + $json.body.error : '' }}",
            "additionalFields": {}
        }

data["connections"]["Webhook (Receive Result)"] = {
    "main": [
        [
            {
                "node": "Parse Base64",
                "type": "main",
                "index": 0
            }
        ]
    ]
}
data["connections"]["Parse Base64"] = {
    "main": [
        [
            {
                "node": "Send Final Image",
                "type": "main",
                "index": 0
            }
        ]
    ]
}

with open(filepath, "w") as f:
    json.dump(data, f, indent=2)

print("JSON updated")
