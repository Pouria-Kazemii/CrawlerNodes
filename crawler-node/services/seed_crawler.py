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
                result = {
                    "type": "seed",
                    "original_url": urls,
                    "error": 'Missing or invalid urls (must be an array)',
                    "meta": config.get("meta") ,
                    "is_last": True,
                    'status_code' : 400
                }
                send_result_to_laravel(result)
                return '',400
            
            if not meta or not isinstance(urls, list):
                result = {
                    "type": "seed",
                    "original_url": urls,
                    "error": 'Missing or invalid meta (must be an array)',
                    "meta": config.get("meta"),
                    "is_last": True ,
                    'status_code' : 400
                }
                send_result_to_laravel(result)
                return '', 400   

            options = config.get("options", {})
            delay = int(options.get("crawl_delay", 1))
            max_depth = int(options.get("max_depth", 1))
            headers = options.get("headers", {})
            selector = options.get("selector")

            # You provide this directly as a list of path substrings
            include_patterns = options.get("link_filter_rules", [])

            if "User-Agent" not in headers:
                headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36"
                )

            visited = set()
            queue = [(url, 0) for url in urls]

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=not DEBUG_MODE,
                    slow_mo=200 if DEBUG_MODE else 0
                )
                context = await browser.new_context(extra_http_headers=headers)
                page = await context.new_page()

                while queue:
                    current_url, depth = queue.pop(0)
                    if current_url in visited or depth > max_depth:
                        continue

                    visited.add(current_url)
                    is_last = len(queue) == 0

                    try:
                        await page.goto(current_url, timeout=10000)
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(delay)

                        # Extract all links on the page
                        if selector != 'null':
                            links = await page.eval_on_selector_all(
                                f"{selector} a[href]",
                                "elements => elements.map(e => e.href)"
                            )
                        else:
                            links = await page.eval_on_selector_all(
                                "a[href]",
                                "elements => elements.map(e => e.href)"
                            )

                        # Filter links
                        matched_links = self._apply_filters(links, include_patterns)

                        # Send only filtered result (NO HTML)
                        result = {
                            "type": "seed",
                            "original_url": current_url,
                            "final_url": page.url,
                            "content": matched_links,
                            "meta": config.get("meta") ,
                            "is_last": is_last,
                            'status_code': 200
                        }
                        send_result_to_laravel(result)

                        # Add filtered links to queue for further crawling
                        for link in matched_links:
                            if link not in visited:
                                queue.append((link, depth + 1))

                    except Exception as e:
                        send_result_to_laravel({
                            "type": "seed",
                            "original_url": current_url,
                            "error": str(e),
                            "meta": meta ,
                            "is_last": is_last,
                            'status_code':500
                        })

                await browser.close()

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _apply_filters(self, links, include_substrings):
        """
        Return only links that contain at least one of the given substrings
        Example: include_substrings = ['/fa/news', '/fa/zxc']
        Will match: https://site.com/abc/fa/zxc/123
        """
        if not include_substrings:
            return links  # No filtering needed

        filtered = []
        for link in links:
            if any(sub in link for sub in include_substrings):
                filtered.append(link)
        return filtered
