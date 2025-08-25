import asyncio
from playwright.async_api import async_playwright
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel
from config import DEBUG_MODE


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
                browser = await p.chromium.launch(
                    headless=not DEBUG_MODE,
                    slow_mo=200 if DEBUG_MODE else 0
                )
                context = await browser.new_context(extra_http_headers=headers)
                page = await context.new_page()

                for index, url in enumerate(urls):
                    current_url = url
                    while current_url and count < limit:
                        try:
                            await page.goto(current_url, timeout=15000)
                            await page.wait_for_load_state("networkidle")
                            await asyncio.sleep(delay)

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
                                "is_last": index == len(urls) - 1,
                                'status_code': 200
                            }
                        
                            send_result_to_laravel(result)
                            count += 1

                            next_btn = await page.query_selector(next_selector)
                            if next_btn:
                                    try:
                                        await asyncio.gather(
                                            page.wait_for_navigation(),
                                            next_btn.click()
                                        )
                                        current_url = page.url
                                    except Exception:
                                        href = await next_btn.get_attribute("href")
                                        if href:
                                            from urllib.parse import urljoin
                                            current_url = urljoin(page.url, href)
                                        else:
                                            break
                                    else:
                                        break
                        except Exception as page_error:  # Renamed to avoid confusion
                            error_result = {
                            "type": "paginated",
                            "original_url": url,
                            "error": str(page_error),
                            "meta": config.get("meta"),
                            "is_last": index == len(urls) - 1,
                            'status_code': 500
                            }
                            send_result_to_laravel(error_result)

                await browser.close()

        except Exception as e:
            return {"status": "error", "message": str(e)}
