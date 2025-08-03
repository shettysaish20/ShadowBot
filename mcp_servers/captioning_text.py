import base64
import requests
import json
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"
GEMMA_MODEL = "gemma3:12b"

def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def get_caption_from_image(image_path: str) -> str:
    encoded_image = encode_image(image_path)

    headers = {"Content-Type": "application/json"}
    payload = {
        "model": GEMMA_MODEL,
        "prompt": (
            "Look only at the attached image. If it's code, output it exactly as text. "
            "If it's a visual scene, describe it as you would for an image alt-text. "
            "Never generate new code. Return only the contents of the image."
        ),
        "images": [encoded_image],
        "stream": True
    }

    print(f"\n📤 Sending image to {GEMMA_MODEL} via Ollama...")

    try:
        response = requests.post(OLLAMA_URL, headers=headers, json=payload, stream=True)
        caption_parts = []

        for line in response.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
                chunk = data.get("response", "")
                caption_parts.append(chunk)
                if data.get("done", False):
                    break
            except json.JSONDecodeError:
                continue

        final_caption = "".join(caption_parts).strip()
        if not final_caption:
            return "[❌ No caption returned]"
        if final_caption.lower().startswith("def ") or "class " in final_caption:
            return f"[🧠 Code detected]\n{final_caption}"
        return final_caption

    except Exception as e:
        return f"[ERROR] {str(e)}"

if __name__ == "__main__":
    raw_input = input("📷 Enter path to image: ").strip()
    image_path = Path(raw_input.strip('"')).expanduser()

    if not image_path.exists():
        print("❌ Invalid file path.")
    else:
        caption = get_caption_from_image(str(image_path))
        print("\n📋 Caption:\n", caption)
