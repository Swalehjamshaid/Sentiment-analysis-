async def fetch_reviews(
    place_id: str,
    limit: int = 150,
    **kwargs
) -> List[Dict[str, Any]]:
    reviews: List[Dict[str, Any]] = []
    seen = set()

    url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ]
            )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="Asia/Karachi",
                bypass_csp=True,
            )

            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            logger.info(f"Starting reviews scrape for place_id: {place_id}")

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Consent
            try:
                await page.get_by_role("button", name=re.compile(r"(accept all|agree|ok|continue|accept|got it)", re.I)).click(timeout=10000)
                await asyncio.sleep(random.uniform(1.5, 3.0))
            except:
                pass

            # Open Reviews tab (your current working strategies)
            tab_found = False
            tab_strategies = [
                page.get_by_role("tab", name=re.compile(r"reviews?|جائزے|تقييمات", re.I)),
                page.get_by_role("tab", name=re.compile(r"\d.*reviews?", re.I)),
                page.locator('[aria-label*="review" i], [aria-label*="جائزہ" i], [aria-label*="تقييم" i]'),
                page.get_by_text(re.compile(r"reviews?|جائزے|تقييمات", re.I)).first,
                page.locator('//div[@role="tablist"]//div[contains(@role,"tab")][contains(translate(text(),"REVIEWS","reviews"),"reviews")]'),
            ]

            for locator in tab_strategies:
                try:
                    if await locator.count() > 0:
                        first_tab = locator.first
                        await first_tab.scroll_into_view_if_needed(timeout=5000)
                        await first_tab.click(delay=random.randint(150, 450), timeout=15000, force=True)
                        await asyncio.sleep(random.uniform(3.0, 5.0))
                        await page.wait_for_selector("div.jftiEf, [data-review-id]", timeout=25000)
                        tab_found = True
                        logger.info("Reviews panel successfully opened")
                        break
                except Exception as exc:
                    logger.debug(f"Tab strategy failed: {exc}")
                    continue

            if not tab_found:
                logger.warning("All attempts to open Reviews tab failed")
                await browser.close()
                return []

            # ── IMPROVED SCROLL & COLLECTION ──
            # Find the scrollable reviews container (common in 2026)
            scroll_container_selector = 'div[role="main"] div[role="feed"], div[aria-label*="reviews"], div.m6QErb[aria-label*="reviews"]'

            max_scroll_attempts = 40  # increased cap
            attempts_no_new = 0
            prev_len = 0

            for attempt in range(max_scroll_attempts):
                # Expand all "More"
                more_btns = page.get_by_role("button", name=re.compile(r"more|مزید", re.I))
                count_more = await more_btns.count()
                logger.debug(f"Expanding {count_more} 'More' buttons")
                for i in range(min(count_more, 15)):
                    try:
                        await more_btns.nth(i).click(timeout=3000, force=True)
                        await asyncio.sleep(0.4 + random.random() * 0.6)
                    except:
                        pass

                # Collect current visible cards
                cards = await page.query_selector_all("div.jftiEf, [data-review-id]")
                logger.debug(f"Attempt {attempt+1}: Found {len(cards)} review cards visible")

                added_this_round = 0
                for card in cards:
                    try:
                        author_el = await card.query_selector(".d4r55")
                        author = (await author_el.inner_text() if author_el else "Anonymous").strip()

                        text_el = await card.query_selector(".wiI7pd")
                        text = (await text_el.inner_text() if text_el else "").strip()

                        rating_el = await card.query_selector('[aria-label*="star"]')
                        rating_text = await rating_el.get_attribute("aria-label") if rating_el else ""
                        rating_match = re.search(r"\d+", rating_text)
                        rating = int(rating_match.group()) if rating_match else 0

                        date_el = await card.query_selector(".rsqaWe")
                        date_str = (await date_el.inner_text() if date_el else "").strip()
                        time_iso = parse_relative_date(date_str).isoformat()

                        unique_key = hashlib.sha256(f"{author}|{text[:120]}|{rating}".encode()).hexdigest()
                        if unique_key in seen:
                            continue

                        reviews.append({
                            "review_id": unique_key,
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": time_iso,
                        })
                        seen.add(unique_key)
                        added_this_round += 1

                    except:
                        continue

                current_len = len(reviews)
                logger.info(f"Scroll attempt {attempt+1}: Total reviews now {current_len} (added {added_this_round} this round)")

                if current_len >= limit:
                    logger.info(f"Reached limit of {limit} reviews")
                    break

                if current_len == prev_len:
                    attempts_no_new += 1
                    if attempts_no_new >= 8:  # lowered threshold
                        logger.info("No new reviews loaded for several attempts → stopping scroll")
                        break
                else:
                    attempts_no_new = 0
                prev_len = current_len

                # Scroll the reviews pane specifically
                try:
                    container = page.locator(scroll_container_selector).first
                    if await container.is_visible():
                        await container.evaluate("el => el.scrollTop = el.scrollHeight")
                        await asyncio.sleep(random.uniform(3.0, 6.0))  # longer wait for lazy load
                        # Optional: fallback mouse scroll if needed
                        await page.mouse.wheel(0, random.randint(1200, 2500))
                    else:
                        await page.evaluate("window.scrollBy(0, 2000)")
                except:
                    await page.evaluate("window.scrollBy(0, 2200)")

                await asyncio.sleep(random.uniform(1.0, 2.5))  # extra breathing room

            logger.info(f"Finished collection – total {len(reviews)} reviews gathered")
            await browser.close()
            return reviews[:limit]

    except Exception as e:
        logger.error(f"Scraper error: {e}", exc_info=True)
        return []
