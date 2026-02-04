import json
import re
import io
from openai import OpenAI

import config

client = OpenAI(api_key=config.OPENAI_API_KEY)


def extract_from_text(text: str) -> dict:
    """Extract expense data from text using OpenAI."""
    prompt = f"""
Extract expense data as strict JSON with keys:
date (YYYY-MM-DD or blank), vendor, amount (number), currency (symbol or code), category (one-word like Food, Transport, SaaS, Utilities, Uncategorized), notes.

Text:
{text}

Return ONLY valid JSON object.
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300
        )
        content = resp.choices[0].message.content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            content = re.sub(r'^```(?:json)?\n?', '', content)
            content = re.sub(r'\n?```$', '', content)

        data = json.loads(content)
    except Exception:
        # Fallback: try to extract amount with regex
        m = re.search(r'([$€£])\s?(\d+(?:\.\d{1,2})?)', text)
        amount = float(m.group(2)) if m else None
        data = {
            "date": "",
            "vendor": "",
            "amount": amount,
            "currency": (m.group(1) if m else ""),
            "category": "Uncategorized",
            "notes": text
        }
    return data


def extract_from_receipt_image(image_bytes: bytes) -> dict:
    """Extract expense data from receipt image using OCR."""
    try:
        from PIL import Image
        import pytesseract

        img = Image.open(io.BytesIO(image_bytes))
        ocr_text = pytesseract.image_to_string(img)
        return extract_from_text(ocr_text)
    except Exception:
        # Fallback if OCR fails
        return extract_from_text("[image attached - could not extract text]")
