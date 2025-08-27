import asyncio
from playwright.async_api import async_playwright
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel
from config import DEBUG_MODE


class StaticCrawler(BaseCrawler):
    def crawl(self, config):
        return asyncio.run(self._crawl_static(config))

    async def _crawl_static(self, config):
        try:
            urls = config.get("urls")
            meta = config.get("meta")

            if not urls or not isinstance(urls, list):
                send_result_to_laravel({
                    "type": "static",
                    "original_url": urls,
                    "error": 'Missing or invalid urls (must be an array)',
                    "meta": meta,
                    "is_last": True,
                    'status_code': 400
                })
                return '', 400

            if not meta or not isinstance(meta, dict):
                send_result_to_laravel({
                    "type": "static",
                    "original_url": urls,
                    "error": 'Missing or invalid meta (must be an object)',
                    "meta": meta,
                    "is_last": True,
                    'status_code': 400
                })
                return '', 400

            options = config.get("options", {})
            delay = int(options.get("crawl_delay", 0))
            headers = options.get("headers", {})
            selectors = options.get("selectors", [])  # Must be a list of dicts

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
                # Set longer timeouts for Docker environment
                context.set_default_timeout(30000)
                page = await context.new_page()
                page.set_default_timeout(30000)

                for index, url in enumerate(urls):
                    try:
                        # Enhanced navigation with better error handling
                        try:
                            await page.goto(url, timeout=15000, wait_until='domcontentloaded')
                            await page.wait_for_load_state("networkidle", timeout=10000)
                            await asyncio.sleep(delay)
                        except Exception as nav_error:
                            send_result_to_laravel({
                                "type": "static",
                                "original_url": url,
                                "error": f"Navigation failed: {str(nav_error)}",
                                "meta": meta,
                                "is_last": index == len(urls) - 1,
                                'status_code': 500
                            })
                            continue  # Continue with next URL

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

                                extracted_data[field] = field_contents

                            except Exception:
                                extracted_data[field] = []

                        send_result_to_laravel({
                            "type": "static",
                            "original_url": url,
                            "final_url": page.url,
                            "content": extracted_data,
                            "meta": meta,
                            "is_last": index == len(urls) - 1,
                            'status_code': 200
                        })

                    except Exception as page_error:
                        send_result_to_laravel({
                            "type": "static",
                            "original_url": url,
                            "error": str(page_error),
                            "meta": meta,
                            "is_last": index == len(urls) - 1,
                            'status_code': 500
                        })

                await browser.close()

        except Exception as main_error:
            send_result_to_laravel({
                "type": "static",
                "original_url": urls[0] if urls else '',
                "error": f"Unhandled error: {str(main_error)}",
                "meta": meta,
                "is_last": True,
                'status_code': 500
            })
            return {"status": "error", "message": str(main_error)}