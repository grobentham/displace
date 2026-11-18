import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for w,h in [(1440,900),(1280,800)]:
            pg=await b.new_page(viewport={'width':w,'height':h}); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
            await pg.route('**/fonts.g*',lambda r:r.abort())
            await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1200)
            await pg.evaluate("document.querySelector('#bDrill').click()"); await pg.locator('#mFoot .primary').click(); await pg.wait_for_timeout(300)
            print(w, await pg.evaluate('JSON.stringify([$("#top").offsetHeight,$("#rp").offsetHeight])'),errs)
            await pg.screenshot(path=f's16_{w}.png')
        await b.close()
asyncio.run(main())
