# translations/fix_english_to_ojibwe.py
from pymongo import MongoClient
from decouple import config

# MongoDB connection setup
client = MongoClient(config("MONGO_URI"))
db = client["vota_db"]
english_to_ojibwe = db["english_to_ojibwe"]

# Fetch all documents
documents = list(english_to_ojibwe.find())

# Swap english_text and ojibwe_text for each document
for doc in documents:
    english_text = doc["english_text"]
    ojibwe_text = doc["ojibwe_text"]
    definition = doc.get("definition", "")

    # Check if english_text looks like an Ojibwe word (simplified check)
    # We can assume that if english_text contains Ojibwe characters or patterns, it's incorrect
    # For simplicity, we'll swap all entries, but you can add more sophisticated checks
    english_to_ojibwe.update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "english_text": ojibwe_text,
            "ojibwe_text": english_text,
            "definition": definition
        }}
    )

print(f"Updated {len(documents)} documents in the english_to_ojibwe collection.")
client.close()
