import asyncio
from playwright.async_api import async_playwright , TimeoutError as PlaywrightTimeoutError
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel
from config import DEBUG_MODE


class SeedCrawler(BaseCrawler):
    def crawl(self, config):
        return asyncio.run(self._crawl_seed(config))

    async def _crawl_seed(self, config):
        try:
            urls = config.get("urls")
            meta = config.get("meta")

            if not urls or not isinstance(urls, list):
                send_result_to_laravel({
                    "type": "seed",
                    "original_url": urls,
                    "error": "Missing or invalid urls (must be an array)",
                    "meta": meta,
                    "is_last": True,
                    "status_code": 400
                })
                return '', 400

            if not meta:
                send_result_to_laravel({
                    "type": "seed",
                    "original_url": urls,
                    "error": "Missing meta",
                    "meta": meta,
                    "is_last": True,
                    "status_code": 400
                })
                return '', 400

            options = config.get("options", {})
            delay = int(options.get("crawl_delay", 1))
            headers = options.get("headers", {})
            selector = options.get("selector")
            include_patterns = options.get("link_filter_rules", [])

            if "User-Agent" not in headers:
                headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36"
                )

            async with async_playwright() as p:
                # DOCKER-OPTIMIZED BROWSER LAUNCH
                browser = await p.chromium.launch(
                    headless=True,  # Always headless in Docker
                    args=[
                        '--disable-dev-shm-usage',  # Prevents /dev/shm issues
                        '--no-sandbox',            # Required for Docker
                        '--disable-setuid-sandbox', # Required for Docker
                        '--disable-accelerated-2d-canvas',
                        '--disable-gpu'
                    ]
                )
                
                context = await browser.new_context(extra_http_headers=headers)
                context.set_default_timeout(30000)
                page = await context.new_page()
                page.set_default_timeout(30000)

                for index, url in enumerate(urls):
                    for attempt in range(3 + 1):
                        try:
                            response = await page.goto(url, timeout=15000, wait_until='domcontentloaded')
                            status_code = response.status if response else 500
                            
                            if status_code >= 400:
                                send_result_to_laravel({
                                    "type": "seed",
                                    "original_url": url,
                                    "error": f"HTTP {status_code} received",
                                    "meta": meta,
                                    "is_last": index == len(urls) - 1,
                                    "status_code": status_code
                                })
                                break
                                
                            content_loaded = False
                            
                            try:
                                await page.wait_for_selector(selector, timeout=15000)
                                content_loaded = True
                            except PlaywrightTimeoutError:
                                if DEBUG_MODE:
                                    print(f"Timeout waiting for selector {selector} on {url}")
                                    
                            if not content_loaded and attempt < 3:
                                if DEBUG_MODE:
                                    print(f"Retrying {url} (attempt {attempt + 1}/{3})")
                                await asyncio.sleep(1)  # Brief pause before retry
                                continue        
                                    
                            if selector and selector != 'null':
                                links = await page.eval_on_selector_all(
                                    f"{selector} a[href]",
                                    "elements => elements.map(e => e.href)" 
                                )
                            else:
                                links = await page.eval_on_selector_all(
                                    "a[href]",
                                    "elements => elements.map(e => e.href)"
                                )    
                            
                            matched_links = self._apply_filters(links, include_patterns)
                            extracted_data = list(set(matched_links))
                                
                            if not extracted_data and content_loaded and attempt < 3:
                                if DEBUG_MODE:
                                    print(f"No links found on {url}, retrying (attempt {attempt + 1}/{3})")
                                await asyncio.sleep(1)
                                continue
                                
                            send_result_to_laravel({
                                "type": "seed",
                                "original_url": url,
                                "final_url": page.url,
                                "content": extracted_data,
                                "meta": meta,
                                "is_last": index == len(urls) - 1,
                                "status_code": 200
                            })
                            break
   
                        except Exception as e:
                            if attempt == 3:
                                send_result_to_laravel({
                                    "type": "seed",
                                    "original_url": url,
                                    "error": f"Failed after {3} retries: {str(e)}",
                                    "meta": meta,
                                    "is_last": index == len(urls) - 1,
                                    "status_code": 500
                                })
                            if DEBUG_MODE:
                                print(f"Error on {url}: {str(e)}")
                            await asyncio.sleep(1)  # Pause before retry

                    await asyncio.sleep(delay)  # Delay between URLs

                await browser.close()

        except Exception as e:
            send_result_to_laravel({
                "type": "seed",
                "original_url": urls[0] if urls else '',
                "error": f"Unhandled error: {str(e)}",
                "meta": meta,
                "is_last": True,
                "status_code": 500
            })
            return {"status": "error", "message": str(e)}


    def _apply_filters(self, links, include_substrings):
        if not include_substrings:
            return links
        return [link for link in links if any(sub in link for sub in include_substrings)]