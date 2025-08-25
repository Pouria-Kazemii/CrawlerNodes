import asyncio
from playwright.async_api import async_playwright
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
                browser = await p.chromium.launch(
                    headless=not DEBUG_MODE,
                    slow_mo=200 if DEBUG_MODE else 0
                )
                context = await browser.new_context(extra_http_headers=headers)
                page = await context.new_page()


                for index, url in enumerate(urls):
                    try:
                        await page.goto(url, timeout=15000)
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(delay)
                        
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
                            
                        send_result_to_laravel({
                            "type": "seed",
                            "original_url": url,
                            "final_url": page.url,
                            "content": matched_links,
                            "meta": meta,
                            "is_last": index == len(urls) - 1,
                            "status_code": 200
                        })

                    except Exception as e:
                        send_result_to_laravel({
                            "type": "seed",
                            "original_url": url,
                            "error": str(e),
                            "meta": meta,
                            "is_last": index == len(urls) - 1,
                            "status_code": 500
                        })

                await browser.close()

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _apply_filters(self, links, include_substrings):
        if not include_substrings:
            return links
        return [link for link in links if any(sub in link for sub in include_substrings)]
