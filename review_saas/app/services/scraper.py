async def fetch_all_reviews(place_id: str):

    results = []
    seen_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 2000}
        )

        page = await context.new_page()

        await page.goto(f"https://www.google.com/maps/place/?q=place_id:{place_id}", timeout=60000)
        await asyncio.sleep(5)

        # Open reviews
        try:
            await page.click('button[jsaction*="pane.reviewChart.moreReviews"]', timeout=10000)
        except:
            await page.click('button:has-text("reviews")')

        await asyncio.sleep(5)

        scrollable = page.locator('div[role="feed"]')
        await page.wait_for_selector('div[data-review-id]', timeout=15000)

        last_count = 0
        no_new_rounds = 0

        while True:

            # Scroll deeper
            await scrollable.evaluate("el => el.scrollBy(0, 5000)")
            await asyncio.sleep(random.uniform(1.5, 3))

            # Expand all "More"
            more_buttons = page.locator('button.w8nwRe')
            for i in range(await more_buttons.count()):
                try:
                    await more_buttons.nth(i).click()
                except:
                    pass

            cards = await page.query_selector_all('div[data-review-id]')

            for c in cards:
                try:
                    rid = await c.get_attribute("data-review-id")

                    if not rid or rid in seen_ids:
                        continue

                    seen_ids.add(rid)

                    # Rating
                    rating_el = await c.query_selector('span.kvMYJc')
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else None
                    rating = int(rating_raw[0]) if rating_raw else None

                    # Author
                    author_el = await c.query_selector('.d4r55')
                    author = await author_el.inner_text() if author_el else "Anonymous"

                    # Text
                    text_el = await c.query_selector('.wiI7pd') or await c.query_selector('.bN97Pc')
                    text = await text_el.inner_text() if text_el else ""

                    if not text:
                        continue

                    results.append({
                        "review_id": rid,
                        "author_name": author,
                        "rating": rating,
                        "text": clean_text(text),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

                except:
                    continue

            print(f"Collected: {len(results)}")

            # STOP CONDITION (CRITICAL)
            if len(results) == last_count:
                no_new_rounds += 1
            else:
                no_new_rounds = 0

            if no_new_rounds >= 7:
                print("🚫 No more reviews available")
                break

            last_count = len(results)

        await browser.close()

    return results
