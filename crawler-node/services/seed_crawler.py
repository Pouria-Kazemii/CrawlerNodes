import asyncio
import re
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel

class SeedCrawler(BaseCrawler):
    def crawl(self, config):
        return asyncio.run(self._crawl_seed(config))

    async def _crawl_seed(self, config):
        try:
            base_url = config.get("base_url")
            if not base_url:
                return {"status": "error", "message": "Missing base_url"}

            options = config.get("options", {})
            delay = int(options.get("crawl_delay", 1))
            max_depth = int(options.get("max_depth", 1))
            limit = int(options.get("limit", 50))
            headers = options.get("headers", {})

            filter_rules = options.get("link_filter_rules", {})
            include_patterns = filter_rules.get("include", [])
            exclude_patterns = filter_rules.get("exclude", [])

            if "User-Agent" not in headers:
                headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36"
                )

            # Determine start URLs
            if config.get("start_urls"):
                start_urls = [urljoin(base_url, path) for path in config["start_urls"]]
            elif config.get("url_pattern") and config.get("range"):
                pattern = config["url_pattern"]
                start = config["range"].get("start", 1)
                end = config["range"].get("end", 1)
                start_urls = [pattern.replace("{id}", str(i)) for i in range(start, end + 1)]
            else:
                start_urls = [base_url]

            if config.get("start_urls") and config.get("url_pattern"):
                return {"status": "error", "message": "Cannot use both start_urls and url_pattern"}

            visited = set()
            queue = [(url, 0) for url in start_urls]
            collected = []

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(extra_http_headers=headers)
                page = await context.new_page()

                while queue and len(collected) < limit:
                    current_url, depth = queue.pop(0)
                    if current_url in visited or depth > max_depth:
                        continue

                    visited.add(current_url)

                    try:
                        await page.goto(current_url, timeout=10000)
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(delay)

                        html = await page.content()
                        result = {
                            "type": "seed",
                            "original_url": current_url,
                            "final_url": page.url,
                            "html": html,
                            "meta": config.get("meta", {})
                        }
                        send_result_to_laravel(result)
                        collected.append(current_url)

                        # Collect new links
                        links = await page.eval_on_selector_all(
                            "a[href]",
                            "elements => elements.map(e => e.href)"
                        )

                        for link in self._apply_filters(links, include_patterns, exclude_patterns)[:20]:
                            if link not in visited:
                                queue.append((link, depth + 1))
                                if len(collected) >= limit:
                                    break

                    except Exception as e:
                        send_result_to_laravel({
                            "type": "seed",
                            "original_url": current_url,
                            "error": str(e),
                            "meta": config.get("meta", {})
                        })

                await browser.close()

            return {
                "status": "success",
                "base_url": base_url,
                "count": len(collected)
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _apply_filters(self, links, include, exclude):
        def match_any(patterns, text):
            return any(re.search(p, text) for p in patterns)
        return [link for link in links if (not include or match_any(include, link)) and not match_any(exclude, link)]
