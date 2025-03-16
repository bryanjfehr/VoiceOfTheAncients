import json
with open("data/english_dict.json", "r", encoding="utf-8") as f:
    data = json.load(f)
    print(type(data), list(data.items())[:5])