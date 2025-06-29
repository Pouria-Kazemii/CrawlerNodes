import asyncio
import time
import re
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from services.base_crawler import BaseCrawler

class SeedCrawler(BaseCrawler):
    def crawl(self, url, options=None):
        return asyncio.run(self._crawl_seed(url, options or {}))

    async def _crawl_seed(self, start_url, options):
        try:
            limit = int(options.get("limit", 50))
            max_depth = int(options.get("max_depth", 1))
            delay = int(options.get("crawl_delay", 1))
            headers = options.get("headers", {})

            filter_rules = options.get("link_filter_rules", {})
            include_patterns = filter_rules.get("include", [])
            exclude_patterns = filter_rules.get("exclude", [])

            collected = []
            visited = set()
            queue = [(start_url, 0)]

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
                        await page.goto(current_url, timeout=15000)
                        await page.wait_for_load_state("networkidle")

                        links = await page.eval_on_selector_all(
                            "a[href^='http']",
                            "elements => elements.map(e => e.href)"
                        )

                        # Filter links
                        filtered_links = self._apply_filters(links, include_patterns, exclude_patterns)

                        for link in filtered_links:
                            if link not in visited:
                                queue.append((link, depth + 1))
                                collected.append(link)
                                if len(collected) >= limit:
                                    break

                        await asyncio.sleep(delay)

                    except Exception as e:
                        # Skip broken pages silently or log
                        continue

                await browser.close()

                return {
                    "status": "success",
                    "url": start_url,
                    "links": collected[:limit],
                    "count": len(collected[:limit])
                }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

    def _apply_filters(self, links, include_patterns, exclude_patterns):
        def match_any(patterns, text):
            return any(re.search(pattern, text) for pattern in patterns)

        result = []
        for link in links:
            if include_patterns and not match_any(include_patterns, link):
                continue
            if exclude_patterns and match_any(exclude_patterns, link):
                continue
            result.append(link)
        return result
