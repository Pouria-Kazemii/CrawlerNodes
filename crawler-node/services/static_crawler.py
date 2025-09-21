import asyncio
import random
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from services.base_crawler import BaseCrawler
from utils.sender import send_result_to_laravel
from config import DEBUG_MODE

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
]

LANGUAGES = ["en-US,en", "en-GB,en", "fa-IR,fa"]

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
            selectors = options.get("selectors", [])
            separate_items = options.get("separate_items", False)

            # Randomize User-Agent if not set
            if "User-Agent" not in headers:
                headers["User-Agent"] = random.choice(USER_AGENTS)

            async with async_playwright() as p:
                browser_args = [
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--window-size=1920,1080',
                ]

                browser = await p.chromium.launch(
                    headless=not DEBUG_MODE,
                    slow_mo=200 if DEBUG_MODE else 0,
                    args=browser_args,
                )

                lang = random.choice(LANGUAGES)
                headers["Accept-Language"] = lang
                context = await browser.new_context(
                    extra_http_headers=headers,
                    viewport={'width': 1920, 'height': 1080},
                    user_agent=headers["User-Agent"],
                    locale=lang.split(',')[0]
                )
                context.set_default_timeout(30000)
                page = await context.new_page()
                page.set_default_timeout(30000)

                stealth = Stealth(
                    navigator_languages_override=tuple(lang.split(',')),
                    init_scripts_only=True
                )
                await stealth.apply_stealth_async(context)

                for index, url in enumerate(urls):
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            await page.goto(url, timeout=15000, wait_until='domcontentloaded')
                            await page.wait_for_load_state("networkidle", timeout=10000)

                            # Mimic human: Random scroll and hover
                            rand = random.uniform(delay+1, delay+3)
                            await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight / {rand});")
                            await page.hover("body")
                            await asyncio.sleep(rand)

                            # Check for bot detection
                            title = await page.title()
                            content = await page.content()
                            if any(indicator in title for indicator in ["Access Denied", "Challenge"]) or "turnstile" in content.lower():
                                raise Exception("Possible bot detection block")
                            
                            if any(missing in title for missing in ["Not Found", "Not Exists"]):
                                send_result_to_laravel({
                                "type": "static",
                                "original_url": url,
                                "final_url": page.url,
                                "content": 'Page Not Exists',
                                "meta": meta,
                                "is_last": index == len(urls) - 1,
                                'status_code': 200
                                })
                                break
                            

                            # Handle container-based extraction (separate_items = true)
                            container_selector = None
                            if separate_items:
                                for selector_item in selectors:
                                    if selector_item.get("key") == "container" or selector_item.get("is_container"):
                                        container_selector = selector_item.get("selector")
                                        break

                            if container_selector:
                                extracted_data = []
                                try:
                                    container_locator = page.locator(container_selector)
                                    containers = await container_locator.all()

                                    for container in containers:
                                        object_data = {}
                                        has_data = False

                                        for selector_item in selectors:
                                            field = selector_item.get("key")
                                            selector = selector_item.get("selector")
                                            full_html = selector_item.get("full_html", False)

                                            if not field or not selector or field == "container":
                                                continue

                                            try:
                                                field_locator = container.locator(selector)
                                                element_count = await field_locator.count()

                                                if element_count > 0:
                                                    element = field_locator.first
                                                    if full_html:
                                                        content = await element.inner_html()
                                                    else:
                                                        raw_text = await element.text_content()
                                                        content = ' '.join([
                                                            t.strip() for t in raw_text.split('\n')
                                                            if t.strip() and t not in ('== %0', '⇔')
                                                        ]) if raw_text else None
                                                    object_data[field] = content.strip() if content else ''
                                                    if content:
                                                        has_data = True
                                                else:
                                                    object_data[field] = ''

                                            except Exception:
                                                object_data[field] = ''

                                        if has_data:
                                            extracted_data.append(object_data)

                                except Exception as e:
                                    extracted_data = []

                            else:
                                extracted_data = {}
                                
                                for selector_item in selectors:
                                    field = selector_item.get("key")
                                    selector = selector_item.get("selector")
                                    full_html = selector_item.get("full_html", False)

                                    if not field or not selector:
                                        continue

                                    try:
                                        locator = page.locator(selector)
                                        elements = await locator.all()
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

                            # Send result
                            send_result_to_laravel({
                                "type": "static",
                                "original_url": url,
                                "final_url": page.url,
                                "content": extracted_data,
                                "meta": meta,
                                "is_last": index == len(urls) - 1,
                                'status_code': 200
                            })

                            break

                        except Exception as nav_error:
                            if attempt < max_retries - 1:
                                headers["User-Agent"] = random.choice(USER_AGENTS)
                                lang = random.choice(LANGUAGES)
                                headers["Accept-Language"] = lang
                                await context.close()
                                context = await browser.new_context(
                                    extra_http_headers=headers,
                                    viewport={'width': 1920, 'height': 1080},
                                    user_agent=headers["User-Agent"],
                                    locale=lang.split(',')[0]
                                )
                                context.set_default_timeout(30000)
                                page = await context.new_page()
                                page.set_default_timeout(30000)
                                stealth = Stealth(
                                    navigator_languages_override=tuple(lang.split(',')),
                                    init_scripts_only=True
                                )
                                await stealth.apply_stealth_async(context)
                                await asyncio.sleep(random.uniform(delay+5, delay+10))
                                continue
                            else:
                                send_result_to_laravel({
                                    "type": "static",
                                    "original_url": url,
                                    "error": f"Navigation failed: {str(nav_error)}",
                                    "meta": meta,
                                    "is_last": index == len(urls) - 1,
                                    'status_code': 500
                                })
                                break

                    if index < len(urls) - 1:
                        await asyncio.sleep(random.uniform(delay+1, delay+3))

                await browser.close()

        except Exception as main_error:
            send_result_to_laravel({
                "type": "static",
                "original_url": urls[0] if urls else '',
                "error": f"Unhandled error: {str(main_error)}",
                "status": "crawl_failed",
                "meta": meta,
                "is_last": True,
                'status_code': 500
            })
            return {"status": "error", "message": str(main_error)}