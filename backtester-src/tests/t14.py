import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for w,h in((1440,900),(390,844)):
            pg=await b.new_page(viewport={'width':w,'height':h}); errs=[]
            pg.on('pageerror',lambda e:errs.append(str(e)))
            await pg.route('**/fonts.g*',lambda r:r.abort())
            await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1500)
            await pg.evaluate("S.tilt=false"); await pg.screenshot(path=f'/tmp/bt2/s22_{w}.png')
            print(w,errs, await pg.evaluate("document.documentElement.scrollWidth"))
        await b.close()
asyncio.run(main())
