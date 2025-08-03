from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.json import JSON
import json
import re
from pathlib import Path
from datetime import datetime
import sys
import os
from html import unescape
import asyncio
import aiohttp
from typing import List, Dict, Optional
import time

# Fix imports for standalone usage
if __name__ == "__main__":
    # Add parent directory to path when running standalone
    sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from agentLoop.contextManager import ExecutionContextManager
except ImportError:
    # If we're running standalone and still can't import, define a minimal stub
    ExecutionContextManager = None

class ImageValidator:
    """Fast and safe image URL validation using async HTTP HEAD requests"""
    
    def __init__(self, timeout: int = 3, max_concurrent: int = 15):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
    
    async def check_image_exists(self, session: aiohttp.ClientSession, url: str) -> Dict:
        """Check if a single image URL exists and is accessible"""
        try:
            async with session.head(
                url, 
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                allow_redirects=True
            ) as response:
                content_type = response.headers.get('content-type', '').lower()
                is_image = any(img_type in content_type for img_type in ['image/', 'jpeg', 'png', 'gif', 'webp'])
                
                return {
                    'url': url,
                    'exists': response.status == 200,
                    'status': response.status,
                    'content_type': content_type,
                    'is_image': is_image,
                    'size': response.headers.get('content-length', 0),
                    'error': None
                }
        except asyncio.TimeoutError:
            return {'url': url, 'exists': False, 'error': 'timeout', 'status': 0}
        except aiohttp.ClientError as e:
            return {'url': url, 'exists': False, 'error': f'client_error: {str(e)}', 'status': 0}
        except Exception as e:
            return {'url': url, 'exists': False, 'error': f'unknown: {str(e)}', 'status': 0}
    
    async def validate_images_batch(self, urls: List[str]) -> List[Dict]:
        """Validate multiple image URLs concurrently"""
        if not urls:
            return []
        
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent, 
            limit_per_host=5,
            ttl_dns_cache=300,
            use_dns_cache=True
        )
        
        timeout = aiohttp.ClientTimeout(total=self.timeout, connect=1)
        
        try:
            async with aiohttp.ClientSession(
                connector=connector, 
                timeout=timeout,
                headers=self.headers
            ) as session:
                # Create tasks for all URLs
                tasks = [self.check_image_exists(session, url) for url in urls]
                
                # Execute with timeout for the entire batch
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=self.timeout * 2  # Give extra time for batch
                )
                
                # Process results and handle exceptions
                processed_results = []
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        processed_results.append({
                            'url': urls[i] if i < len(urls) else 'unknown',
                            'exists': False, 
                            'error': f'exception: {str(result)}',
                            'status': 0
                        })
                    else:
                        processed_results.append(result)
                
                return processed_results
                
        except asyncio.TimeoutError:
            return [{'url': url, 'exists': False, 'error': 'batch_timeout', 'status': 0} for url in urls]
        except Exception as e:
            return [{'url': url, 'exists': False, 'error': f'batch_error: {str(e)}', 'status': 0} for url in urls]
    
    def validate_images_sync(self, urls: List[str]) -> List[Dict]:
        """Synchronous wrapper for async validation"""
        if not urls:
            return []
        
        try:
            # Handle event loop issues
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If there's already a running loop, we need to use a different approach
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self.validate_images_batch(urls))
                        return future.result(timeout=self.timeout * 3)
                else:
                    return loop.run_until_complete(self.validate_images_batch(urls))
            except RuntimeError:
                # No event loop, create new one
                return asyncio.run(self.validate_images_batch(urls))
                
        except Exception as e:
            print(f"⚠️  Image validation failed: {e}")
            return [{'url': url, 'exists': False, 'error': f'sync_wrapper: {str(e)}', 'status': 0} for url in urls]

class OutputAnalyzer:
    def __init__(self, context: ExecutionContextManager = None, validate_images: bool = True):
        """Work directly with NetworkX graph - no intermediate processing"""
        self.context = context
        self.graph = context.plan_graph if context else None
        self.console = Console()
        self.validate_images = validate_images
        self.image_validator = ImageValidator() if validate_images else None
    
    def show_results(self):
        """Display comprehensive results analysis directly from NetworkX graph"""
        
        if not self.context:
            self.console.print("❌ No execution context available")
            return
            
        # Get data directly from graph
        summary = self.context.get_execution_summary()
        
        # 1. Execution Overview
        self.console.print(Panel(
            f"✅ Completed: {summary['completed_steps']}/{summary['total_steps']} steps\n"
            f"💰 Total Cost: ${summary['total_cost']:.2f} ({summary['total_input_tokens']}/{summary['total_output_tokens']})\n"
            f"❌ Failures: {summary['failed_steps']}",
            title="📊 Execution Summary",
            border_style="green"
        ))
        
        # 2. Raw Agent Outputs (from individual nodes)
        self.console.print("\n🔍 **Raw Agent Outputs (from graph nodes):**")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Step")
        table.add_column("Agent")
        table.add_column("Status")
        table.add_column("Raw Output Keys")
        
        for node_id in self.graph.nodes:
            if node_id == "ROOT":
                continue
            node_data = self.graph.nodes[node_id]
            if node_data.get('output'):
                output = node_data['output']
                if isinstance(output, dict):
                    if 'output' in output and isinstance(output['output'], dict):
                        keys = list(output['output'].keys())
                    else:
                        keys = list(output.keys())
                else:
                    keys = ['raw_text']
                
                status = node_data['status']
                if status == 'completed':
                    status = f"[green]✅ {status}[/green]"
                elif status == 'failed':
                    status = f"[red]❌ {status}[/red]"
                
                table.add_row(
                    node_id,
                    node_data.get('agent', 'Unknown'),
                    status,
                    str(keys)
                )
        
        self.console.print(table)
        
        # 3. Session Info directly from graph
        self.console.print(f"\n📋 **Session:** {self.graph.graph['session_id']}")
        self.console.print(f"🕐 **Created:** {self.graph.graph['created_at']}")
        self.console.print(f"📁 **Session File:** memory/session_summaries_index/{self.graph.graph['created_at'][:10].replace('-', '/')}/session_{self.graph.graph['session_id']}.json")

        # Enhanced cost display
        cost_breakdown = summary.get("cost_breakdown", {})
        if cost_breakdown:
            self.console.print(f"\n💰 **Cost Breakdown:**")
            for step, data in cost_breakdown.items():
                cost = data["cost"]
                input_tokens = data["input_tokens"]
                output_tokens = data["output_tokens"]
                self.console.print(f"   • {step}: ${cost:.6f} ({input_tokens}/{output_tokens})")
            self.console.print(f"   **Total: ${summary['total_cost']:.6f}**")
        else:
            self.console.print(f"💰 Total Cost: ${summary['total_cost']:.4f}")

        # 4. Auto-extract HTML report if available
        self.extract_and_save_html_report()

    def extract_and_save_html_report(self):
        """Extract HTML report from session and save as proper HTML file"""
        try:
            if not self.graph:
                self.console.print("\n⚠️  No graph data available")
                return None
                
            session_id = self.graph.graph['session_id']
            
            # Find the HTML report in the graph
            html_content = self._find_html_report()
            
            if html_content:
                # Create proper HTML structure
                full_html = self._create_proper_html(html_content, session_id, self.context.get_session_data())
                
                # Save to file
                output_path = Path(f"memory/session_{session_id}_report.html")
                output_path.write_text(full_html, encoding='utf-8')
                
                self.console.print(f"\n📄 **Seraphine Report Generated:** {output_path}")
                return str(output_path)
            else:
                self.console.print("\n⚠️  No HTML report found in session data")
                return None
                
        except Exception as e:
            self.console.print(f"\n❌ Error generating HTML report: {e}")
            return None

    def _find_html_report(self):
        """SIMPLIFIED: Find HTML report directly from output_chain"""
        if not self.graph:
            return None
        
        session_id = self.graph.graph['session_id']
        
        # ✅ STRATEGY 1: Check for auto-saved HTML file (keep this)
        html_file_path = Path(f"media/generated/{session_id}/formatted_report.html")
        if html_file_path.exists():
            try:
                html_content = html_file_path.read_text(encoding='utf-8')
                self.console.print(f"📄 Found auto-saved HTML report: {html_file_path}")
                return html_content
            except Exception as e:
                self.console.print(f"⚠️  Could not read saved HTML file: {e}")
        
        # ✅ STRATEGY 2: Check output_chain directly for HTML content
        output_chain = self.graph.graph.get('output_chain', {})
        
        # Look for FormatterAgent outputs with HTML content
        for step_id, output_data in output_chain.items():
            if isinstance(output_data, dict):
                # Check top-level fields for HTML
                for key, value in output_data.items():
                    if isinstance(value, str) and _looks_like_html_content_standalone(value):
                        self.console.print(f"📄 Found HTML in output_chain: {step_id}.{key}")
                        return value
                
                # Check nested fields
                if 'output' in output_data and isinstance(output_data['output'], dict):
                    for key, value in output_data['output'].items():
                        if isinstance(value, str) and _looks_like_html_content_standalone(value):
                            self.console.print(f"📄 Found HTML in output_chain: {step_id}.output.{key}")
                            return value

        # ✅ STRATEGY 3: Fallback to node scanning (keep as final fallback)
        self.console.print("🔍 Scanning FormatterAgent outputs in graph...")
        for node_id in self.graph.nodes:
            if node_id == "ROOT":
                continue
            
            node_data = self.graph.nodes[node_id]
            
            if node_data.get('agent') == 'FormatterAgent' and node_data.get('output'):
                output = node_data['output']
                
                # Check all string fields for HTML content
                for key, value in output.items():
                    if isinstance(value, str) and _looks_like_html_content_standalone(value):
                        self.console.print(f"📄 Found HTML in graph field: {key}")
                        return value
                
                # Check nested output structure
                if 'output' in output and isinstance(output['output'], dict):
                    for key, value in output['output'].items():
                        if isinstance(value, str) and _looks_like_html_content_standalone(value):
                            self.console.print(f"📄 Found HTML in nested field: {key}")
                            return value

        return None

    def _looks_like_html_content(self, content):
        """Check if content looks like HTML"""
        if not isinstance(content, str) or len(content) < 10:
            return False
        
        content_start = content.strip()[:100].lower()
        html_indicators = [
            '<html', '<div', '<section', '<article', '<header', 
            '<main', '<body', '<!doctype', '<h1', '<h2', '<p'
        ]
        
        return any(indicator in content_start for indicator in html_indicators)

    def _extract_images_from_session_data(self, session_data):
        """Extract all images by brute force URL search with detailed logging AND validation"""
        images = []
        all_urls = set()
        processed_count = 0
        
        try:
            print(f"🔍 Brute force search for image URLs...")
            
            # Convert entire session to searchable text
            session_text = json.dumps(session_data)
            print(f"📝 Searching {len(session_text):,} characters of session data...")
            
            # Find ALL image URLs using regex
            image_urls = re.findall(
                r'https?://[^\s\'"<>\\]+\.(?:jpg|jpeg|png|webp|gif)(?:\?[^\s\'"<>\\]*)?', 
                session_text, 
                re.IGNORECASE
            )
            
            print(f"🎯 Raw URL matches found: {len(image_urls)}")
            
            for i, url in enumerate(image_urls):
                processed_count += 1
                
                # Check for duplicates
                if url in all_urls:
                    continue
                
                all_urls.add(url)
                clean_url = url.rstrip('",\'\\')
                
                # ✅ FILTER 1: Social media URL check (FIXED - removed the else continue bug)
                if self._is_social_media_image(clean_url):
                    continue
                
                # Extract metadata from context
                alt_text = f"Image {len(images) + 1}"
                confidence_score = 0.85  # Default confidence
                width = height = None
                
                # Look for metadata patterns near this URL in the full text
                url_index = session_text.find(url)
                if url_index != -1:
                    context = session_text[max(0, url_index-500):url_index+len(url)+500]
                    
                    # Extract confidence score
                    confidence_patterns = [
                        r"['\"]confidence['\"]:\s*([0-9.]+)",
                        r"confidence['\"]:\s*([0-9.]+)"
                    ]
                    
                    for pattern in confidence_patterns:
                        conf_matches = re.findall(pattern, context)
                        if conf_matches:
                            try:
                                confidence_score = float(conf_matches[0])
                            except:
                                pass
                            break
                    
                    # Extract dimensions
                    width_patterns = [
                        r"['\"]width['\"]:\s*['\"]?(\d+)['\"]?",
                        r"width['\"]:\s*['\"]?(\d+)['\"]?"
                    ]
                    height_patterns = [
                        r"['\"]height['\"]:\s*['\"]?(\d+)['\"]?",
                        r"height['\"]:\s*['\"]?(\d+)['\"]?"
                    ]
                    
                    for pattern in width_patterns:
                        width_matches = re.findall(pattern, context)
                        if width_matches:
                            try:
                                width = int(width_matches[0])
                            except:
                                pass
                            break
                    
                    for pattern in height_patterns:
                        height_matches = re.findall(pattern, context)
                        if height_matches:
                            try:
                                height = int(height_matches[0])
                            except:
                                pass
                            break
                    
                    # Extract alt text
                    alt_patterns = [
                        r"['\"]alt_text['\"]:\s*['\"]([^'\"]+)['\"]",
                        r"['\"]alt['\"]:\s*['\"]([^'\"]+)['\"]",
                        r"alt_text['\"]:\s*['\"]([^'\"]+)",
                        r"alt['\"]:\s*['\"]([^'\"]+)"
                    ]
                    
                    for pattern in alt_patterns:
                        alt_matches = re.findall(pattern, context)
                        if alt_matches:
                            alt_text = alt_matches[0]
                            break
                
                # ✅ FILTER 2: Confidence score check
                if confidence_score < 0.69:
                    continue
                
                # ✅ FILTER 3: Size checks
                if width and height:
                    if width < 500 or height < 500:
                        continue
                    
                    # Aspect ratio check
                    aspect_ratio = max(width, height) / min(width, height)
                    if aspect_ratio > 4:
                        continue
                
                elif width and not height:
                    if width < 500:
                        continue
                
                elif height and not width:
                    print(f"📐 Checking height only: {height}px")
                    if height < 500:
                        continue
                
                # ✅ FILTER 4: Alt text check
                if self._is_social_media_alt_text(alt_text):
                    continue
                
                # ✅ FILTER 5: Low quality URL patterns
                if self._is_low_quality_url(clean_url):
                    continue
                
                # ✅ ALL FILTERS PASSED - Add to results
                images.append({
                    'url': clean_url,
                    'alt_text': alt_text,
                    'source': 'session_data',
                    'confidence': confidence_score,
                    'width': width,
                    'height': height
                })
            
            # ✅ NEW: VALIDATE URLs if enabled
            if self.validate_images and self.image_validator and images:
                print(f"🌐 Validating {len(images)} candidate images...")
                start_time = time.time()
                
                urls_to_check = [img['url'] for img in images]
                validation_results = self.image_validator.validate_images_sync(urls_to_check)
                
                # Filter out broken images
                valid_images = []
                for img, validation in zip(images, validation_results):
                    if validation.get('exists', False) and validation.get('is_image', True):
                        valid_images.append(img)
                        print(f"✅ Valid: {img['url'][:60]}...")
                    else:
                        error = validation.get('error', 'unknown')
                        status = validation.get('status', 0)
                        print(f"❌ Invalid ({status}/{error}): {img['url'][:60]}...")
                
                validation_time = time.time() - start_time
                print(f"⏱️  Validation completed in {validation_time:.2f}s")
                print(f"📊 Valid images: {len(valid_images)}/{len(images)}")
                
                images = valid_images
            
            print(f"\n🎯 FINAL SUMMARY:")
            print(f"   Total URLs found: {len(image_urls)}")
            print(f"   Unique URLs processed: {len(all_urls)}")
            print(f"   Images passing filters: {len(images)}")
            print(f"   Image validation: {'✅ Enabled' if self.validate_images else '❌ Disabled'}")
            
            return images[:12]  # Return top 12 valid images
            
        except Exception as e:
            print(f"❌ Error in image extraction: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _is_social_media_image(self, url):
        """Check if URL suggests a social media image"""
        social_media_keywords = [
            'facebook', 'twitter', 'instagram', 'linkedin', 'youtube', 
            'whatsapp', 'telegram', 'email', 'share', 'social',
            'icon', 'logo', 'btn', 'button', 'arrow'
        ]
        
        url_lower = url.lower()
        return any(keyword in url_lower for keyword in social_media_keywords)

    def _is_social_media_alt_text(self, alt_text):
        """Check if alt text suggests social media content"""
        if not alt_text:
            return False
        
        social_media_keywords = [
            'share on', 'facebook', 'twitter', 'instagram', 'linkedin',
            'whatsapp', 'email', 'social', 'follow us', 'like us',
            'subscribe', 'icon', 'logo', 'button'
        ]
        
        alt_lower = alt_text.lower()
        return any(keyword in alt_lower for keyword in social_media_keywords)

    def _is_low_quality_url(self, url):
        """Check for low-quality URL patterns"""
        low_quality_patterns = [
            r'/icon[s]?/',           # Icon directories
            r'/button[s]?/',         # Button directories
            r'/social/',             # Social media directories
            r'/share/',              # Share button directories
            r'/arrow[s]?/',          # Arrow images
            r'/bg[_-]',              # Background images
            r'/banner[s]?/',         # Banner directories
            r'/ad[s]?/',             # Advertisement directories
            r'_icon\.',              # Files ending with _icon
            r'_btn\.',               # Files ending with _btn
            r'_arrow\.',             # Files ending with _arrow
            r'_logo\.',              # Files ending with _logo
            r'pixel\.', r'spacer\.', # Spacer/pixel images
            r'blank\.', r'empty\.',  # Blank/empty images
        ]
        
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in low_quality_patterns)

    def _create_image_carousel(self, images):
        """Create HTML carousel for images"""
        if not images:
            return ""
        
        carousel_html = """
        <div class="image-carousel">
            <div class="carousel-container">
                <div class="carousel-slides">
        """
        
        for i, img in enumerate(images):
            active_class = "active" if i == 0 else ""
            confidence_display = f"{img.get('confidence', 0.0):.2f}" if isinstance(img.get('confidence'), (int, float)) else img.get('confidence', 'N/A')
            
            # Extract domain from URL for source link
            source_link = self._extract_source_link(img['url'])
            
            carousel_html += f"""
                    <div class="carousel-slide {active_class}">
                        <img src="{img['url']}" alt="{img['alt_text']}" />
                        <div class="carousel-caption">
                            <p><strong>{img['alt_text']}</strong></p>
                            <small>{source_link} | Confidence: {confidence_display}</small>
                        </div>
                    </div>
            """
        
        # Only show navigation if there are multiple images
        nav_buttons = ""
        if len(images) > 1:
            nav_buttons = """
                <button class="carousel-btn prev" onclick="changeSlide(-1)">&lt;</button>
                <button class="carousel-btn next" onclick="changeSlide(1)">&gt;</button>
            """
        
        carousel_html += f"""
                </div>
                {nav_buttons}
            </div>
        """
        
        # Only show dots if there are multiple images
        if len(images) > 1:
            carousel_html += '<div class="carousel-dots">'
            for i in range(len(images)):
                active_class = "active" if i == 0 else ""
                carousel_html += f'<button class="carousel-dot {active_class}" onclick="currentSlide({i + 1})"></button>'
            carousel_html += '</div>'
        
        carousel_html += """
        </div>
        """
        
        return carousel_html

    def _extract_source_link(self, url):
        """Extract domain from URL and create a clickable link"""
        try:
            import re
            # Extract domain from URL
            domain_match = re.match(r'https?://([^/]+)', url)
            if domain_match:
                domain = domain_match.group(1)
                # Remove www. if present for cleaner display
                display_domain = domain.replace('www.', '')
                return f'<a href="//{domain}" target="_blank" rel="noopener noreferrer">Source: {display_domain}</a>'
            else:
                return 'Source: session_data'
        except:
            return 'Source: session_data'

    def _get_carousel_css(self):
        """Get CSS for the image carousel"""
        return """
        /* Image Carousel Styles */
        .image-carousel {
            margin: 2rem 0;
        }
        
        .carousel-container {
            position: relative;
            max-width: 100%;
            margin: auto;
        }
        
        .carousel-slides {
            display: flex;
            overflow: hidden;
            width: 100%;
        }
        
        .carousel-slide {
            min-width: 100%;
            display: none;
            flex-direction: column;
            align-items: center;
        }
        
        .carousel-slide.active {
            display: flex;
        }
        
        .carousel-slide img {
            width: 100%;
            max-height: 500px;
            object-fit: contain;
            border-radius: 4px;
        }
        
        .carousel-caption {
            text-align: center;
            margin-top: 1rem;
            max-width: 600px;
        }
        
        .carousel-caption p {
            margin: 0.5rem 0;
            font-weight: 500;
        }
        
        .carousel-caption small {
            color: #666;
            font-size: 0.8rem;
        }
        html.dark .carousel-caption small, body.dark .carousel-caption small {
            color: #aaa;
        }
        
        .carousel-btn {
            position: absolute;
            top: 45%;
            transform: translateY(-50%);
            background: rgba(0,0,0,0.6);
            color: white;
            border: none;
            padding: 0.8rem 1rem;
            cursor: pointer;
            font-size: 0.5rem;
            border-radius: 4px;
            transition: all 0.3s ease;
            z-index: 10;
            opacity: 0.7;
        }
        
        .carousel-btn:hover {
            background: rgba(0,0,0,0.9);
            opacity: 1;
            transform: translateY(-50%) scale(1.1);
        }
        
        .carousel-btn.prev {
            left: 0;
        }
        
        .carousel-btn.next {
            right: 0;
        }
        
        .carousel-dots {
            text-align: center;
            padding: 1rem 0;
        }
        
        .carousel-dot {
            height: 8px;
            width: 8px;
            margin: 0 4px;
            background-color: #ccc;
            border-radius: 50%;
            display: inline-block;
            cursor: pointer;
            border: none;
            transition: all 0.3s ease;
        }
        
        .carousel-dot.active, .carousel-dot:hover {
            background-color: #333;
            transform: scale(1.2);
        }
        html.dark .carousel-dot {
            background-color: #666;
        }
        html.dark .carousel-dot.active, body.dark .carousel-dot.active,
        html.dark .carousel-dot:hover, body.dark .carousel-dot:hover {
            background-color: #ccc;
        }
        """

    def _get_carousel_javascript(self):
        """Get JavaScript for the image carousel"""
        return """
        // Image Carousel JavaScript
        let currentSlideIndex = 0;
        let slides = [];
        let dots = [];
        
        function initializeCarousel() {
            slides = document.querySelectorAll('.carousel-slide');
            dots = document.querySelectorAll('.carousel-dot');
            currentSlideIndex = 0;
            
            if (slides.length > 0) {
                showSlide(0);
            }
        }
        
        function showSlide(index) {
            // Hide all slides
            slides.forEach(slide => slide.classList.remove('active'));
            dots.forEach(dot => dot.classList.remove('active'));
            
            // Show selected slide
            if (slides[index]) {
                slides[index].classList.add('active');
                if (dots[index]) {
                    dots[index].classList.add('active');
                }
            }
        }
        
        function changeSlide(direction) {
            if (slides.length === 0) return;
            
            currentSlideIndex += direction;
            if (currentSlideIndex >= slides.length) currentSlideIndex = 0;
            if (currentSlideIndex < 0) currentSlideIndex = slides.length - 1;
            showSlide(currentSlideIndex);
        }
        
        function currentSlide(index) {
            if (slides.length === 0) return;
            
            currentSlideIndex = index - 1;
            showSlide(currentSlideIndex);
        }
        
        // Initialize carousel when page loads
        document.addEventListener('DOMContentLoaded', function() {
            initializeCarousel();
        });
        
        // Re-initialize if content changes (for emoji toggle)
        window.addEventListener('load', function() {
            setTimeout(initializeCarousel, 100);
        });
        """

    def _create_proper_html(self, html_content, session_id, session_data=None):
        """Create proper HTML with validated image carousel from session data"""
        from datetime import datetime
        import re
        from html import unescape

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # ✅ Strip FormatterAgent styling
        clean_html = html_content
        clean_html = re.sub(r'<style[^>]*>.*?</style>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r'\s+class=["\'][^"\']*["\']', '', clean_html)
        clean_html = re.sub(r'<div[^>]*section-toc[^>]*>.*?</div>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r'<div[^>]*navigation[^>]*>.*?</div>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r'^<div[^>]*>', '', clean_html.strip())
        clean_html = re.sub(r'</div>$', '', clean_html.strip())
        clean_html = re.sub(r'<(div|span)[^>]*></\1>', '', clean_html)
        clean_html = re.sub(r'\s+style=["\'][^"\']*["\']', '', clean_html)
        
        # ✅ NEW: Clean up problematic inline image styles
        clean_html = re.sub(r'<img([^>]*)\s+style=["\'][^"\']*width[^"\']*["\']([^>]*)>', 
                          r'<img\1\2>', clean_html)
        clean_html = re.sub(r'<img([^>]*)\s+style=["\'][^"\']*height[^"\']*["\']([^>]*)>', 
                          r'<img\1\2>', clean_html)
        
        # ✅ GENERIC: Move ANY content above first H1 to after H1
        content_before_h1 = ""
        h1_pattern = r'(<h1[^>]*>.*?</h1>)'
        h1_match = re.search(h1_pattern, clean_html, re.IGNORECASE | re.DOTALL)
        
        if h1_match:
            h1_start_pos = h1_match.start()
            h1_end_pos = h1_match.end()
            
            # Extract content before H1
            if h1_start_pos > 0:
                content_before_h1 = clean_html[:h1_start_pos].strip()
                # Remove the content before H1 from the original
                clean_html = clean_html[h1_start_pos:]
                
                # Find the H1 again in the cleaned content
                h1_match_new = re.search(h1_pattern, clean_html, re.IGNORECASE | re.DOTALL)
                if h1_match_new:
                    h1_end_pos_new = h1_match_new.end()
                    # Insert the extracted content after H1
                    clean_html = (clean_html[:h1_end_pos_new] + 
                                content_before_h1 + 
                                clean_html[h1_end_pos_new:])
        
        # ✅ EXTRACT AND CREATE CAROUSEL
        carousel_html = ""
        carousel_css = ""
        carousel_js = ""
        
        if session_data:
            images = self._extract_images_from_session_data(session_data)
            if images:
                carousel_html = self._create_image_carousel(images)
                carousel_css = self._get_carousel_css()
                carousel_js = self._get_carousel_javascript()
        
        # ✅ INSERT CAROUSEL AFTER FIRST HEADING (now that content is properly ordered)
        if carousel_html:
            heading_pattern = r'(<h[12][^>]*>.*?</h[12]>)'
            match = re.search(heading_pattern, clean_html, re.IGNORECASE)
            if match:
                heading_end_pos = match.end()
                clean_html = (clean_html[:heading_end_pos] + 
                            carousel_html + 
                            clean_html[heading_end_pos:])
            else:
                clean_html = carousel_html + clean_html
        
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', clean_html)
        title = title_match.group(1) if title_match else f"Session {session_id} Report"
        title_clean = re.sub(r'<[^>]+>', '', title)

        # ✅ UPDATED: Get carousel CSS and add content image CSS
        content_image_css = """
        /* Content Images Styling */
        .container img:not(.carousel-slide img) {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 1.5rem auto;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        html.dark .container img:not(.carousel-slide img), 
        body.dark .container img:not(.carousel-slide img) {
            box-shadow: 0 2px 8px rgba(255,255,255,0.1);
        }
        
        /* Remove any remaining inline width/height styles */
        .container img[style*="width"] {
            width: auto !important;
            max-width: 100% !important;
        }
        .container img[style*="height"] {
            height: auto !important;
        }
        """
        
        # Combine all CSS
        all_css = carousel_css + content_image_css
        
        # ✅ VALIDATE inline images in HTML content
        if self.validate_images:
            clean_html = self._validate_inline_images_in_html(clean_html)
        
        return rf"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title_clean}</title>
  <style>
    /* Base styles */
    :root {{
      --bg-light: #ffffff;
      --bg-dark: #0a0a0a;
      --text-light: #111111;
      --text-dark: #f1f1f1;
      --border-light: #000000;
      --border-dark: #ffffff;
      --font-sans: 'Inter', 'San Francisco', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      --font-serif: 'EB Garamond', 'New York', 'Georgia', serif;
    }}

    html, body {{
      margin: 0;
      padding: 0;
      font-family: var(--font-sans);
      font-size: 18px;
      background-color: var(--bg-light);
      color: var(--text-light);
      line-height: 1.75;
      transition: background 0.3s, color 0.3s, font-family 0.3s;
    }}
    
    html.dark, body.dark {{
      background-color: var(--bg-dark);
      color: var(--text-dark);
    }}

    .container {{
      max-width: 900px;
      margin: 60px auto;
      padding: 0 20px;
      background-color: var(--bg-light);
      transition: background-color 0.3s;
    }}
    html.dark .container, body.dark .container {{
      background-color: var(--bg-dark);
    }}

    h1, h2, h3, h4, h5, h6 {{
      font-weight: 600;
      margin-top: 2.5em;
      margin-bottom: 0.8em;
      line-height: 1.3;
    }}

    h1 {{
      font-size: 2.2rem;
      border-bottom: 0.5px solid var(--border-light);
      padding-bottom: 0.2em;
    }}
    html.dark h1, body.dark h1 {{
      border-color: var(--border-dark);
    }}

    h2 {{
      font-size: 1.5rem;
    }}

    ul, ol {{
      padding-left: 1.5rem;
      margin: 1rem 0;
    }}

    p {{
      margin-bottom: 1rem;
    }}

    .controls {{
      position: fixed;
      top: 12px;
      right: 16px;
      display: flex;
      gap: 14px;
      font-size: 0.9rem;
      z-index: 999;
    }}

    .controls button {{
      all: unset;
      cursor: pointer;
      padding: 2px 6px;
      background: rgba(255, 255, 255, 0.05);
      border-radius: 4px;
      font-weight: 500;
      color: inherit;
      opacity: 0.6;
      transition: opacity 0.3s, background-color 0.3s;
    }}
    .controls button:hover {{
      opacity: 1;
    }}
    html.dark .controls button, body.dark .controls button {{
      background: rgba(255, 255, 255, 0.1);
    }}

    .footer {{
      font-size: 0.55rem;
      text-align: center;
      margin-top: 2rem;
      color: #aaa;
    }}

    @media print {{
      .controls {{ display: none; }}
    }}

    {all_css}
  </style>
</head>
<body>
  <div class="controls">
    <button onclick="toggleDark()">Th</button>
    <button onclick="toggleFont()">Aa</button>
    <button onclick="toggleEmojis()">Em</button>
  </div>
  <div class="container" id="main-container">
    {clean_html}
    <div class="footer">
      <p>Generated by Seraphine on {timestamp} · Session ID: {session_id}</p>
    </div>
  </div>
  <script>
    let emojisHidden = true; /* Start with emojis hidden */
    let originalContent = '';

    function toggleDark() {{
      /* Toggle dark class on BOTH html and body elements */
      document.documentElement.classList.toggle('dark');
      document.body.classList.toggle('dark');
    }}

    function toggleFont() {{
      const current = getComputedStyle(document.body).fontFamily;
      const isSerif = current.includes("Georgia");
      document.body.style.fontFamily = isSerif ? 'var(--font-sans)' : 'var(--font-serif)';
    }}

    function toggleEmojis() {{
      const container = document.getElementById('main-container');
      
      if (emojisHidden) {{
        /* Restore original content (show emojis) */
        if (originalContent) {{
          container.innerHTML = originalContent;
        }}
        emojisHidden = false;
      }} else {{
        /* Store original content and remove emojis */
        if (!originalContent) {{
          originalContent = container.innerHTML;
        }}
        /* ✅ FIXED: Comprehensive emoji regex that includes ALL emoji ranges */
        const emojiRegex = /[\u{{1F300}}-\u{{1F9FF}}]|[\u{{2600}}-\u{{26FF}}]|[\u{{2700}}-\u{{27BF}}]|[\u{{2100}}-\u{{214F}}]|[\u{{1F000}}-\u{{1F02F}}]|[\u{{1F0A0}}-\u{{1F0FF}}]|[\u{{1F100}}-\u{{1F64F}}]|[\u{{1F680}}-\u{{1F6FF}}]|[\u{{1F910}}-\u{{1F96B}}]|[\u{{1F980}}-\u{{1F9E0}}]/gu;
        container.innerHTML = container.innerHTML.replace(emojiRegex, '');
        emojisHidden = true;
      }}
    }}

    /* Initialize with emojis hidden on page load */
    window.addEventListener('load', function() {{
      const container = document.getElementById('main-container');
      /* Store original content first */
      originalContent = container.innerHTML;
      /* Then remove emojis by default */
      /* ✅ FIXED: Same comprehensive emoji regex */
      const emojiRegex = /[\u{{1F300}}-\u{{1F9FF}}]|[\u{{2600}}-\u{{26FF}}]|[\u{{2700}}-\u{{27BF}}]|[\u{{2100}}-\u{{214F}}]|[\u{{1F000}}-\u{{1F02F}}]|[\u{{1F0A0}}-\u{{1F0FF}}]|[\u{{1F100}}-\u{{1F64F}}]|[\u{{1F680}}-\u{{1F6FF}}]|[\u{{1F910}}-\u{{1F96B}}]|[\u{{1F980}}-\u{{1F9E0}}]/gu;
      container.innerHTML = container.innerHTML.replace(emojiRegex, '');
    }});

    {carousel_js}
  </script>
</body>
</html>"""

    def _validate_inline_images_in_html(self, html_content: str) -> str:
        """Validate and clean up inline images in HTML content"""
        if not self.validate_images or not self.image_validator:
            return html_content
        
        # Extract image URLs from HTML
        img_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
        img_matches = re.findall(img_pattern, html_content, re.IGNORECASE)
        
        if not img_matches:
            return html_content
        
        print(f"🖼️  Validating {len(img_matches)} inline images in HTML...")
        
        # Validate all found images
        validation_results = self.image_validator.validate_images_sync(img_matches)
        
        # Create a mapping of URL -> validation result
        url_validation = {result['url']: result for result in validation_results}
        
        # Replace broken images with placeholder or remove them
        def replace_broken_image(match):
            img_tag = match.group(0)
            img_url = match.group(1)
            
            validation = url_validation.get(img_url, {'exists': False})
            
            if validation.get('exists', False):
                return img_tag  # Keep valid images
            else:
                # Replace with placeholder or remove
                print(f"🚫 Removing broken inline image: {img_url[:60]}...")
                return f'<!-- Broken image removed: {img_url} -->'
        
        # Apply replacements
        cleaned_html = re.sub(img_pattern, replace_broken_image, html_content, flags=re.IGNORECASE)
        
        return cleaned_html

def get_meaningful_keys(output):
    """Filter internal keys"""
    if not isinstance(output, dict):
        return []
    
    skip_keys = {'cost', 'input_tokens', 'output_tokens', 'total_tokens', 'execution_result', 'execution_status', 'execution_error', 'execution_time', 'executed_variant'}
    return [k for k in output.keys() if k not in skip_keys]

# Usage in main.py
def analyze_results(context):
    """Analyze results directly from NetworkX graph"""
    analyzer = OutputAnalyzer(context)
    analyzer.show_results()

# Standalone function for external use
def extract_html_report_from_session_file(session_file_path):
    """Extract HTML report from a session JSON file and save as HTML"""
    console = Console()
    
    try:
        session_path = Path(session_file_path)
        if not session_path.exists():
            console.print(f"❌ Session file not found: {session_file_path}")
            return None
            
        console.print(f"📖 Loading session file: {session_path}")
        
        # Load session data
        with open(session_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        # Extract session ID
        session_id = session_data.get('graph', {}).get('session_id', 'unknown')
        console.print(f"🔍 Processing session: {session_id}")
        
        # ✅ USE SAME LOGIC AS MAIN APPLICATION
        html_content = None
        
        # ✅ STRATEGY 1: Check for auto-saved HTML file
        html_file_path = Path(f"media/generated/{session_id}/formatted_report.html")
        if html_file_path.exists():
            try:
                html_content = html_file_path.read_text(encoding='utf-8')
                console.print(f"📄 Found auto-saved HTML report: {html_file_path}")
            except Exception as e:
                console.print(f"⚠️  Could not read saved HTML file: {e}")
        
        # ✅ STRATEGY 2: Check output_chain directly (MISSING FROM ORIGINAL)
        if not html_content:
            output_chain = session_data.get('graph', {}).get('output_chain', {})
            console.print(f"🔍 Checking output_chain with {len(output_chain)} entries...")
            
            # Look for FormatterAgent outputs with HTML content
            for step_id, output_data in output_chain.items():
                if isinstance(output_data, dict):
                    # Check top-level fields for HTML
                    for key, value in output_data.items():
                        if isinstance(value, str) and _looks_like_html_content_standalone(value):
                            html_content = value
                            console.print(f"📄 Found HTML in output_chain: {step_id}.{key}")
                            break
                    
                    if html_content:
                        break
                    
                    # Check nested fields
                    if 'output' in output_data and isinstance(output_data['output'], dict):
                        for key, value in output_data['output'].items():
                            if isinstance(value, str) and _looks_like_html_content_standalone(value):
                                html_content = value
                                console.print(f"📄 Found HTML in output_chain: {step_id}.output.{key}")
                                break
                    
                    if html_content:
                        break
        
        # ✅ STRATEGY 3: Check nodes as fallback (ORIGINAL LOGIC)
        if not html_content:
            nodes = session_data.get('nodes', [])
            console.print(f"🔍 Scanning {len(nodes)} nodes for HTML content...")
            
            for node in nodes:
                if node.get('agent') == 'FormatterAgent' and node.get('output'):
                    console.print(f"   • Found FormatterAgent: {node.get('id')}")
                    output = node['output']
                    
                    # Check all string fields for HTML content
                    for key, value in output.items():
                        if isinstance(value, str) and _looks_like_html_content_standalone(value):
                            html_content = value
                            console.print(f"   ✅ Found HTML report in field: {key}")
                            break
                    
                    if html_content:
                        break
                    
                    # Check nested output structure
                    if 'output' in output and isinstance(output['output'], dict):
                        for key, value in output['output'].items():
                            if isinstance(value, str) and _looks_like_html_content_standalone(value):
                                html_content = value
                                console.print(f"   ✅ Found HTML in nested field: {key}")
                                break
                    
                    if html_content:
                        break
        
        if html_content:
            # ✅ Extract images from session data
            analyzer = OutputAnalyzer()
            
            # Create proper HTML using utility method WITH session data for images
            full_html = analyzer._create_proper_html(html_content, session_id, session_data)
            
            # Save to file
            output_path = session_path.parent / f"session_{session_id}_report.html"
            output_path.write_text(full_html, encoding='utf-8')
            
            console.print(f"✅ HTML Report Generated: {output_path}")
            console.print(f"📊 Report size: {len(full_html):,} characters")
            return str(output_path)
        else:
            console.print("⚠️  No HTML report found in session file")
            console.print("   💡 Searched auto-saved files, output_chain, and FormatterAgent nodes")
            
            # Debug: Show what we found
            output_chain = session_data.get('graph', {}).get('output_chain', {})
            console.print(f"   📊 output_chain keys: {list(output_chain.keys())}")
            
            nodes = session_data.get('nodes', [])
            formatter_nodes = [n for n in nodes if n.get('agent') == 'FormatterAgent']
            console.print(f"   📊 FormatterAgent nodes: {len(formatter_nodes)}")
            
            return None
            
    except Exception as e:
        console.print(f"❌ Error extracting HTML report: {e}")
        import traceback
        console.print(f"   Details: {traceback.format_exc()}")
        return None

def _looks_like_html_content_standalone(content):
    """Standalone version of HTML content checker"""
    if not isinstance(content, str) or len(content) < 10:
        return False
    
    content_start = content.strip()[:100].lower()
    html_indicators = [
        '<html', '<div', '<section', '<article', '<header', 
        '<main', '<body', '<!doctype', '<h1', '<h2', '<p'
    ]
    
    return any(indicator in content_start for indicator in html_indicators)

# CLI usage
if __name__ == "__main__":
    if len(sys.argv) > 1:
        session_file = sys.argv[1]
        extract_html_report_from_session_file(session_file)
    else:
        print("Usage: python output_analyzer.py <session_file.json>")
        print("Example: python output_analyzer.py memory/session_summaries_index/2025/06/30/session_51279586.json")



# uv run agentLoop/output_analyzer.py memory/session_summaries_index/2025/07/02/session_51439952.json