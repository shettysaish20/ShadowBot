# web_tools_async.py
import asyncio
import traceback
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from readability import Document
import trafilatura
import random
from pathlib import Path

DIFFICULT_WEBSITES_PATH = Path(__file__).parent / "difficult_websites.txt"

def get_random_headers():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 Chrome/113.0.5672.92 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/605.1.15 Version/16.3 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 Chrome/117.0.5938.132 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-G998B) AppleWebKit/537.36 Chrome/92.0.4515.159 Mobile Safari/537.36 SamsungBrowser/15.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 Version/16.6 Mobile Safari/604.1"
    ]
    return {"User-Agent": random.choice(user_agents)}


def is_difficult_website(url: str) -> bool:
    if not DIFFICULT_WEBSITES_PATH.exists():
        return False
    try:
        with open(DIFFICULT_WEBSITES_PATH, "r", encoding="utf-8") as f:
            difficult_sites = [line.strip().lower() for line in f if line.strip()]
        return any(domain in url.lower() for domain in difficult_sites)
    except Exception as e:
        print(f"⚠️ Failed to read difficult_websites.txt: {e}")
        return False

# Make sure these utilities exist
def ascii_only(text: str) -> str:
    return text.encode("ascii", errors="ignore").decode()

def choose_best_text(visible, main, trafilatura_):
    # Simple heuristic: prefer main if long, fallback otherwise
    scores = {
        "visible": len(visible.strip()),
        "main": len(main.strip()),
        "trafilatura": len(trafilatura_.strip())
    }
    best = max(scores, key=scores.get)
    return {
        "visible": visible,
        "main": main,
        "trafilatura": trafilatura_
    }[best], best

async def web_tool_playwright(url: str, max_total_wait: int = 15) -> dict:
    result = {"url": url}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Wait until the page body has significant content (i.e., text is non-trivial)
            try:
                await page.wait_for_function(
                    """() => {
                        const body = document.querySelector('body');
                        return body && (body.innerText || "").length > 1000;
                    }""",
                    timeout=15000
                )
            except Exception as e:
                print("⚠️ Generic wait failed:", e)

            # Optional light sleep for residual JS rendering
            await asyncio.sleep(5)

            try:
                await page.evaluate("""() => {
                    window.stop();
                    document.querySelectorAll('script').forEach(s => s.remove());
                }""")
            except Exception as e:
                print("⚠️ JS stop failed:", e)

            html = await page.content()
            visible_text = await page.inner_text("body")
            title = await page.title()
            await browser.close()

            # Run parsing in background to free browser early
            try:
                main_text = await asyncio.to_thread(lambda: BeautifulSoup(Document(html).summary(), "html.parser").get_text(separator="\n", strip=True))
            except Exception as e:
                print("⚠️ Readability failed:", e)
                main_text = ""

            try:
                trafilatura_text = await asyncio.to_thread(lambda: trafilatura.extract(html) or "")
            except Exception as e:
                print("⚠️ Trafilatura failed:", e)
                trafilatura_text = ""

            best_text, source = choose_best_text(visible_text, main_text, trafilatura_text)

            result.update({
                "title": title,
                "html": html,
                "text": visible_text,
                "main_text": main_text,
                "trafilatura_text": trafilatura_text,
                "best_text": ascii_only(best_text),
                "best_text_source": source
            })

    except PlaywrightTimeoutError:
        result.update({
            "title": "[timeout: goto]",
            "html": "",
            "text": "[timed out]",
            "main_text": "[no HTML extracted]",
            "trafilatura_text": "",
            "best_text": "[no text]",
            "best_text_source": "timeout"
        })

    except Exception as e:
        traceback.print_exc()
        result.update({
            "title": "[error]",
            "html": "",
            "text": f"[error: {e}]",
            "main_text": "[no HTML extracted]",
            "trafilatura_text": "",
            "best_text": "[no text]",
            "best_text_source": "error"
        })

    return result

import httpx

async def smart_web_extract(url: str, timeout: int = 5) -> dict:

    headers = get_random_headers()

    try:

        if is_difficult_website(url):
            print(f"Detected difficult site ({url}) → skipping fast scrape")
            return await web_tool_playwright(url)


        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            html = response.content.decode("utf-8", errors="replace")

        doc = Document(html)
        main_html = doc.summary()
        main_text = BeautifulSoup(main_html, "html.parser").get_text(separator="\n", strip=True)
        visible_text = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
        trafilatura_text = trafilatura.extract(html)
        best_text, best_source = choose_best_text(visible_text, main_text, trafilatura_text)
        
        # ✅ NEW: Extract images
        images = extract_images_from_html(html, url)

        if len(best_text) >= 300:
            return {
                "url": url,
                "title": Document(html).short_title(),
                "html": html,
                "text": visible_text,
                "main_text": main_text,
                "trafilatura_text": trafilatura_text,
                "best_text": ascii_only(best_text),
                "best_text_source": best_source,
                "images": images  # ✅ NEW: Image data
            }

        print("Fast scrape too small, falling back...")

    except Exception as e:
        print("Fast scrape failed:", e)

    # Fallback
    return await web_tool_playwright(url)


if __name__ == "__main__":
    print("starting scrape subprocess...")
    import sys
    import json

    if len(sys.argv) != 2:
        print("Usage: python web_tool_playwright_async.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    print("🚀 Trying smart scrape first...")
    result = asyncio.run(smart_web_extract(url))
    print(json.dumps(result, ensure_ascii=False))

def extract_images_from_html(html: str, base_url: str) -> list:
    """Extract curated images with token-efficient output"""
    soup = BeautifulSoup(html, "html.parser")
    images = []
    
    # Find all img tags
    img_tags = soup.find_all('img')
    
    for img in img_tags:
        src = img.get('src', '')
        if not src:
            continue
            
        # Convert relative URLs to absolute
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            from urllib.parse import urljoin
            src = urljoin(base_url, src)
        elif not src.startswith(('http://', 'https://')):
            from urllib.parse import urljoin
            src = urljoin(base_url, src)
        
        # ✅ STRICT FORMAT FILTERING: Only jpg, jpeg, png, webp
        if not _is_valid_image_format(src):
            continue
            
        # ✅ CONFIDENCE FILTERING: Only high-confidence images
        confidence_score = _calculate_image_confidence(src, img)
        if confidence_score < 0.7:  # 70% confidence threshold
            continue
        
        # ✅ TOKEN-EFFICIENT: Only include non-empty fields
        image_data = {'url': src}
        
        # Add optional fields only if they have meaningful values
        alt_text = img.get('alt', '').strip()
        if alt_text:
            image_data['alt_text'] = alt_text
            
        title = img.get('title', '').strip() 
        if title:
            image_data['title'] = title
            
        width = img.get('width', '').strip()
        if width:
            image_data['width'] = width
            
        height = img.get('height', '').strip()
        if height:
            image_data['height'] = height
            
        class_attr = ' '.join(img.get('class', [])).strip()
        if class_attr:
            image_data['class'] = class_attr
            
        loading = img.get('loading', '').strip()
        if loading:
            image_data['loading'] = loading
        
        # Add confidence score for FormatterAgent decision-making
        image_data['confidence'] = confidence_score
        
        images.append(image_data)
    
    # Sort by confidence and return top 5
    images.sort(key=lambda x: x['confidence'], reverse=True)
    return images[:5]

def _is_valid_image_format(src: str) -> bool:
    """Check if image URL has acceptable format"""
    src_lower = src.lower()
    
    # ✅ STRICT: Only jpg, jpeg, png, webp
    valid_formats = ['.jpg', '.jpeg', '.png', '.webp']
    
    # Check if URL ends with valid format
    if any(src_lower.endswith(fmt) for fmt in valid_formats):
        return True
    
    # Check if URL contains valid format with query params
    if any(fmt in src_lower for fmt in valid_formats):
        return True
        
    return False

def _calculate_image_confidence(src: str, img_tag) -> float:
    """Calculate confidence score for image relevance (0.0 to 1.0)"""
    confidence = 0.0
    
    # Base confidence
    confidence += 0.3
    
    # ✅ POSITIVE SIGNALS
    
    # Strong alt text (+0.4)
    alt_text = img_tag.get('alt', '').strip()
    if len(alt_text) > 10:
        confidence += 0.4
    elif len(alt_text) > 3:
        confidence += 0.2
    
    # Meaningful dimensions (+0.2)
    width = img_tag.get('width', '')
    height = img_tag.get('height', '')
    try:
        if width and height:
            w, h = int(width), int(height)
            if w >= 200 and h >= 150:  # Reasonable content image size
                confidence += 0.2
    except (ValueError, TypeError):
        pass
    
    # Content-suggesting classes (+0.2)
    class_attr = ' '.join(img_tag.get('class', [])).lower()
    content_classes = ['hero', 'feature', 'product', 'gallery', 'main', 'content', 'article']
    if any(cls in class_attr for cls in content_classes):
        confidence += 0.2
    
    # High-quality image indicators (+0.1)
    if any(indicator in src.lower() for indicator in ['hd', 'high-res', 'large', '2x', '3x']):
        confidence += 0.1
    
    # ✅ NEGATIVE SIGNALS
    
    # Skip patterns (-0.8)
    skip_patterns = [
        'favicon', 'icon', 'logo', 'sprite', 'pixel', 'tracking',
        'ad.', 'ads.', 'banner', 'button', 'arrow', '1x1', 'donate'
    ]
    
    src_lower = src.lower()
    if any(pattern in src_lower for pattern in skip_patterns):
        confidence -= 0.8
    
    # Skip icon classes (-0.5)
    if any(cls in class_attr for cls in ['icon', 'sprite', 'emoji', 'avatar', 'donate']):
        confidence -= 0.5
    
    # Tiny images (-0.3)
    try:
        if width and height:
            w, h = int(width), int(height)
            if w < 100 or h < 100:
                confidence -= 0.3
    except (ValueError, TypeError):
        pass
    
    return max(0.0, min(1.0, confidence))  # Clamp between 0-1