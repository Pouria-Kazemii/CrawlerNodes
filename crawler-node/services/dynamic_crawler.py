import asyncio
from playwright.async_api import async_playwright
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel

class DynamicCrawler(BaseCrawler):
    def crawl(self, config):
        return asyncio.run(self._crawl_dynamic(config))

    async def _crawl_dynamic(self, config):
        try:
            base_url = config.get("base_url")
            start_url = config.get("start_url", base_url)
            options = config.get("options", {})
            headers = options.get("headers", {})

            scroll = options.get("scroll", False)
            scroll_steps = int(options.get("scroll_steps", 20))
            scroll_delay = int(options.get("scroll_delay", 100))

            click_selector = options.get("click_selector")
            click_times = int(options.get("click_times", 0))

            delay = int(options.get("crawl_delay", 1))

            if "User-Agent" not in headers:
                headers["User-Agent"] = "Mozilla/5.0 Chrome"

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(extra_http_headers=headers)
                page = await context.new_page()

                await page.goto(start_url, timeout=30000)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(delay)

                # click "load more" button if specified
                for _ in range(click_times):
                    try:
                        btn = await page.query_selector(click_selector)
                        if not btn:
                            break
                        await asyncio.gather(
                            page.wait_for_load_state("networkidle"),
                            btn.click()
                        )
                        await asyncio.sleep(1)
                    except Exception:
                        break

                # scroll to bottom
                if scroll:
                    await page.evaluate(f"""
                        async () => {{
                            const delay = {scroll_delay};
                            const steps = {scroll_steps};
                            for (let i = 0; i < steps; i++) {{
                                window.scrollBy(0, window.innerHeight / 2);
                                await new Promise(r => setTimeout(r, delay));
                            }}
                        }}
                    """)
                    await asyncio.sleep(1)

                html = await page.content()
                send_result_to_laravel({
                    "type": "dynamic",
                    "original_url": start_url,
                    "final_url": page.url,
                    "html": html,
                    "meta": config.get("meta", {})
                })

                await browser.close()

            return {"status": "success", "base_url": base_url}

        except Exception as e:
            return {"status": "error", "message": str(e)}
