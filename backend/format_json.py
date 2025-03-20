# backend/format_json.py
import json
import os

# Define the path to the JSON file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_JSON_PATH = os.path.join(BASE_DIR, "data", "english_dict.json")
OUTPUT_JSON_PATH = os.path.join(BASE_DIR, "data", "english_dict_formatted.json")

def format_json_file(input_path: str, output_path: str) -> None:
    """Read a JSON file and rewrite it with proper formatting.

    Args:
        input_path (str): Path to the input JSON file.
        output_path (str): Path to the output formatted JSON file.
    """
    try:
        # Read the JSON file
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Write the formatted JSON file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)

        print(f"Successfully formatted JSON file. Saved to {output_path}")
        print(f"Number of entries: {len(data)}")

    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}")
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON file: {e}")
    except Exception as e:
        print(f"Error: An unexpected error occurred: {e}")

if __name__ == "__main__":
    format_json_file(INPUT_JSON_PATH, OUTPUT_JSON_PATH)
