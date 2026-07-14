import json
import mimetypes
import os

import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ------------------------------------
# Paths / config
# ------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_FOLDER = os.path.join(BASE_DIR, "images")
OUTPUT_XLSX = os.path.join(BASE_DIR, "output.xlsx")

load_dotenv(os.path.join(BASE_DIR, ".env"))

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise SystemExit("GEMINI_API_KEY is missing — paste it into the .env file")

MODEL = "gemini-2.5-flash"

client = genai.Client(api_key=API_KEY)

PROMPT = """\
This image is a page from a handwritten register with one or more tables.

Extract every table. Use the printed column headings exactly as they appear
in the image. Expand ditto marks (", -"-, etc.) to the actual repeated value
from the row above. Values like project name, date, temperature, slump or
grade are often written only once for a group of rows: repeat them in every
row of that group so no cell that logically has a value is left empty. Keep
handwritten values as written; if a value is unreadable, use "?".

Return JSON only, in this shape:
{
  "tables": [
    {
      "title": "<short name for the table>",
      "headers": ["<column heading>", ...],
      "rows": [["<cell>", ...], ...]
    }
  ]
}
Every row must have exactly as many cells as there are headers
(use "" for empty cells).
"""

supported = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".heic")

sheets = []

for filename in sorted(os.listdir(IMAGE_FOLDER)):

    if not filename.lower().endswith(supported):
        continue

    image_path = os.path.join(IMAGE_FOLDER, filename)

    print(f"Processing {filename}...")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    try:
        tables = json.loads(response.text)["tables"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Could not parse response for {filename}: {e}")
        continue

    for i, table in enumerate(tables):
        headers = table.get("headers", [])
        rows = [row[: len(headers)] + [""] * (len(headers) - len(row))
                for row in table.get("rows", [])]

        df = pd.DataFrame(rows, columns=headers)
        df.insert(0, "Filename", filename)

        # Excel sheet names: max 31 chars, no []:*?/\, must be unique
        base = table.get("title") or os.path.splitext(filename)[0]
        base = "".join(c for c in base if c not in '[]:*?/\\')[:27]
        sheet_name = base
        n = 2
        while any(name == sheet_name for name, _ in sheets):
            sheet_name = f"{base}_{n}"
            n += 1

        sheets.append((sheet_name, df))
        print(f"  {table.get('title', sheet_name)}: {len(df)} rows")

if not sheets:
    raise SystemExit("No tables extracted.")

with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
    for sheet_name, df in sheets:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        ws = writer.book[sheet_name]
        for col in ws.columns:
            width = max(len(str(c.value)) for c in col if c.value is not None)
            ws.column_dimensions[col[0].column_letter].width = min(width + 3, 50)

print("\nDone!")
print(f"Saved to {OUTPUT_XLSX}")
