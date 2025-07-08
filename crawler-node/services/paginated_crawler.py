import asyncio
from playwright.async_api import async_playwright
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel

class PaginatedCrawler(BaseCrawler):
    def crawl(self, config):
        return asyncio.run(self._crawl_paginated(config))

    async def _crawl_paginated(self, config):
        try:
            base_url = config.get("base_url")
            start_url = config.get("start_url", base_url)
            next_selector = config.get("next_page_selector")
            if not next_selector:
                return {"status": "error", "message": "Missing next_page_selector"}

            options = config.get("options", {})
            delay = int(options.get("crawl_delay", 1))
            limit = int(options.get("limit", 50))
            headers = options.get("headers", {})

            if "User-Agent" not in headers:
                headers["User-Agent"] = "Mozilla/5.0 Chrome"

            count = 0

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(extra_http_headers=headers)
                page = await context.new_page()

                current_url = start_url
                while current_url and count < limit:
                    try:
                        await page.goto(current_url, timeout=15000)
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(delay)

                        html = await page.content()
                        result = {
                            "type": "paginated",
                            "original_url": current_url,
                            "final_url": page.url,
                            "html": html,
                            "meta": config.get("meta", {})
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
                    except Exception as e:
                        send_result_to_laravel({
                            "type": "paginated",
                            "original_url": current_url,
                            "error": str(e),
                            "meta": config.get("meta", {})
                        })
                        break

                await browser.close()

            return {"status": "success", "base_url": base_url, "count": count}

        except Exception as e:
            return {"status": "error", "message": str(e)}
