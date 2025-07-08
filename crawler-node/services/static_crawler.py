import asyncio
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel

class StaticCrawler(BaseCrawler):
    def crawl(self, config):
        return asyncio.run(self._crawl_static(config))

    async def _crawl_static(self, config):
        try:
            base_url = config.get("base_url")
            if not base_url:
                return {"status": "error", "message": "Missing base_url"}

            options = config.get("options", {})
            headers = options.get("headers", {})

            # Add default User-Agent
            if "User-Agent" not in headers:
                headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36"
                )

            # Build list of URLs
            if config.get("start_urls"):
                urls = [urljoin(base_url, path) for path in config["start_urls"]]
            elif config.get("url_pattern") and config.get("range"):
                pattern = config["url_pattern"]
                start = config["range"].get("start", 1)
                end = config["range"].get("end", 1)
                urls = [pattern.replace("{id}", str(i)) for i in range(start, end + 1)]
            else:
                urls = [base_url]

            if config.get("start_urls") and config.get("url_pattern"):
                return {"status": "error", "message": "Cannot use both start_urls and url_pattern"}

            results = []

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(extra_http_headers=headers)
                page = await context.new_page()

                for url in urls:
                    try:
                        print(f"Crawling: {url}")
                        await page.goto(url, timeout=30000)
                        await page.wait_for_load_state("networkidle")
                        html = await page.content()
                        final_url = page.url

                        result = {
                            "type": "static",
                            "original_url": url,
                            "final_url": final_url,
                            "html": html,
                            "meta": config.get("meta", {})  # optional: job_id, user_id
                        }

                        results.append(result)
                        # send_result_to_laravel(result)

                    except Exception as e:
                        result = {
                            "type": "static",
                            "original_url": url,
                            "error": str(e),
                            "meta": config.get("meta", {})
                        }
                        results.append(result)
                        # send_result_to_laravel(result)

                return {
                    "status": "success",
                    "base_url": base_url,
                    "count": len(results)
                }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
