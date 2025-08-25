import asyncio
from playwright.async_api import async_playwright
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel
from config import DEBUG_MODE

class DynamicCrawler(BaseCrawler):
    def crawl(self, config):
        return asyncio.run(self._crawl_dynamic(config))

    async def _crawl_dynamic(self, config):
        try:
            urls = config.get("urls")
            if not urls or not isinstance(urls, list):
                send_result_to_laravel({
                    "type": "dynamic",
                    "original_url": urls,
                    "error": "Missing or invalid urls (must be an array)",
                    "meta": config.get("meta"),
                    "is_last": True,
                    "status_code": 400
                })
                return '', 400

            options = config.get("options", {})
            delay = int(options.get("crawl_delay", 5))
            headers = options.get("headers", {})
            selectors = options.get("selectors", [])
            max_scrolls = int(options.get("max_scrolls", 5))

            if "User-Agent" not in headers:
                headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36"
                )

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=not DEBUG_MODE,
                    slow_mo=250 if DEBUG_MODE else 0
                )
                context = await browser.new_context(extra_http_headers=headers)
                page = await context.new_page()

                for index, url in enumerate(urls):
                    try:
                        await page.goto(url, timeout=30000)
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(delay)
                        scroll_step=300
                       # Step 2: Detect correct scroll_step
                        while True:
                            previous_height = await page.evaluate("document.body.scrollHeight")
                            
                            await page.mouse.wheel(0, scroll_step)
                            
                            await asyncio.sleep(2)
                            
                            new_height = await page.evaluate("document.body.scrollHeight")
                            
                            if new_height <= previous_height:
                                scroll_step += 100  # increase step to try more scroll next time
                            else:
                                # new content loaded!
                                scroll_step = new_height - previous_height
                                if scroll_step <= 0:
                                    # safety fallback, in case new_height - previous_height is 0 or negative
                                    scroll_step = 100
                                break

                        # Step 3: Scroll for max_scrolls times with working scroll_step
                        for i in range(max_scrolls-1):
                            scroll_step += 140
                            await page.mouse.wheel(0, scroll_step/2)
                            await asyncio.sleep(2)
                            await page.mouse.wheel(0, scroll_step/2)
                            await asyncio.sleep(6)


                        # === Extract Content ===
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
                                for el in elements:
                                    try:
                                        if full_html:
                                            content = await el.inner_html()
                                        else:
                                            text = await el.text_content()
                                            content = ' '.join([
                                                t.strip() for t in text.split('\n')
                                                if t.strip() and t not in ('== %0', '⇔')
                                            ]) if text else None
                                        if content:
                                            field_contents.append(content.strip())
                                    except:
                                        continue
                                extracted_data[field] = field_contents
                            except:
                                extracted_data[field] = []

                        result = {
                            "type": "dynamic",
                            "original_url": url,
                            "final_url": page.url,
                            "content": extracted_data,
                            "meta": config.get("meta"),
                            "is_last": index == len(urls) - 1,
                            "status_code": 200
                        }
                        send_result_to_laravel(result)

                    except Exception as page_error:
                        send_result_to_laravel({
                            "type": "dynamic",
                            "original_url": url,
                            "error": str(page_error),
                            "meta": config.get("meta"),
                            "is_last": index == len(urls) - 1,
                            "status_code": 500
                        })

                await browser.close()

        except Exception as e:
            return {"status": "error", "message": str(e)}
