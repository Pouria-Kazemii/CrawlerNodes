import asyncio
from playwright.async_api import async_playwright
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel
from config import DEBUG_MODE
from urllib.parse import urljoin


class PaginatedCrawler(BaseCrawler):
    def crawl(self, config):
        return asyncio.run(self._crawl_paginated(config))

    async def _crawl_paginated(self, config):
        try:
            urls = config.get("urls")
            if not urls or not isinstance(urls, list):
                result = {
                    "type": "paginated",
                    "original_url": urls,
                    "error": 'Missing or invalid urls (must be an array)',
                    "meta": config.get("meta"),
                    "is_last": True,
                    'status_code' : 400
                }
                send_result_to_laravel(result)
                return '',400
                
            next_selector = config.get("next_page_selector")
            if not next_selector:
                result = {
                    "type": "paginated",
                    "original_url": urls,
                    "error": 'Missing next_page_selector',
                    "meta": config.get("meta"),
                    "is_last": True,
                    'status_code' : 400
                }
                send_result_to_laravel(result)
                return '',400                

            options = config.get("options", {})
            delay = int(options.get("crawl_delay", 1))
            limit = int(options.get("limit", 50))
            headers = options.get("headers", {})
            selectors = options.get("selectors", [])  # Ensure this is a list

            if "User-Agent" not in headers:
                headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36"
                )

            count = 0

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
                # Set longer timeouts for Docker environment
                context.set_default_timeout(30000)
                page = await context.new_page()
                page.set_default_timeout(30000)

                for index, url in enumerate(urls):
                    current_url = url
                    while current_url and count < limit:
                        try:
                            # Enhanced navigation with better error handling
                            try:
                                await page.goto(current_url, timeout=15000, wait_until='domcontentloaded')
                                await page.wait_for_load_state("networkidle", timeout=10000)
                                await asyncio.sleep(delay)
                            except Exception as nav_error:
                                error_result = {
                                    "type": "paginated",
                                    "original_url": current_url,
                                    "error": f"Navigation failed: {str(nav_error)}",
                                    "meta": config.get("meta"),
                                    "is_last": index == len(urls) - 1 and count >= limit - 1,
                                    'status_code': 500
                                }
                                send_result_to_laravel(error_result)
                                break  # Break out of while loop for this URL

                            extracted_data = {}
                            for selector_item in selectors:
                                field = selector_item.get("key")
                                selector = selector_item.get("selector")
                                full_html = selector_item.get("full_html", False)

                                if not field or not selector:
                                    continue

                                try:
                                    elements = await page.query_selector_all(selector)
                                    field_contents = []

                                    for element in elements:
                                        try:
                                            if full_html:
                                                content = await element.inner_html()
                                            else:
                                                raw_text = await element.text_content()
                                                content = ' '.join([
                                                    t.strip() for t in raw_text.split('\n')
                                                    if t.strip() and t not in ('== %0', '⇔')
                                                ]) if raw_text else None
                                            if content:
                                                field_contents.append(content.strip())
                                        except Exception:
                                            continue

                                    extracted_data[field] = field_contents  # this will be a list of values
                                except Exception:
                                    extracted_data[field] = []

                            result = {
                                "type": "paginated",
                                "original_url": url,
                                "final_url": page.url,
                                "content": extracted_data,
                                "meta": config.get("meta"),
                                "is_last": index == len(urls) - 1 and count >= limit - 1,
                                'status_code': 200
                            }
                        
                            send_result_to_laravel(result)
                            count += 1

                            # Handle next page navigation
                            try:
                                next_btn = await page.query_selector(next_selector)
                                if next_btn:
                                    try:
                                        # Wait for navigation with timeout
                                        await asyncio.wait_for(
                                            asyncio.gather(
                                                page.wait_for_navigation(timeout=10000),
                                                next_btn.click()
                                            ),
                                            timeout=15000
                                        )
                                        current_url = page.url
                                    except Exception:
                                        # Fallback to href attribute
                                        href = await next_btn.get_attribute("href")
                                        if href:
                                            current_url = urljoin(page.url, href)
                                        else:
                                            break  # No href, break pagination
                                else:
                                    break  # No next button found
                            except Exception as nav_error:
                                error_result = {
                                    "type": "paginated",
                                    "original_url": current_url,
                                    "error": f"Next page navigation failed: {str(nav_error)}",
                                    "meta": config.get("meta"),
                                    "is_last": index == len(urls) - 1 and count >= limit - 1,
                                    'status_code': 500
                                }
                                send_result_to_laravel(error_result)
                                break

                        except Exception as page_error:
                            error_result = {
                                "type": "paginated",
                                "original_url": current_url,
                                "error": str(page_error),
                                "meta": config.get("meta"),
                                "is_last": index == len(urls) - 1 and count >= limit - 1,
                                'status_code': 500
                            }
                            send_result_to_laravel(error_result)
                            break  # Break out of while loop for this URL

                await browser.close()

        except Exception as e:
            error_result = {
                "type": "paginated",
                "original_url": urls[0] if urls else '',
                "error": f"Unhandled error: {str(e)}",
                "meta": config.get("meta"),
                "is_last": True,
                'status_code': 500
            }
            send_result_to_laravel(error_result)
            return {"status": "error", "message": str(e)}