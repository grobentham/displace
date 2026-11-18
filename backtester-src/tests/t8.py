import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for w,h in [(1440,900),(1180,760),(390,844)]:
            pg=await b.new_page(viewport={'width':w,'height':h}); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
            await pg.route('**/fonts.g*',lambda r:r.abort())
            await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1300)
            print(w, await pg.evaluate('JSON.stringify([$("#top").offsetHeight,$("#rp").offsetHeight,$("#chart").clientWidth,$("#chart").clientHeight,document.documentElement.scrollWidth])'),errs)
            await pg.screenshot(path=f's13_{w}.png')
        await b.close()
asyncio.run(main())
