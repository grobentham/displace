import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for vp in [(1440,900),(390,844)]:
            pg=await b.new_page(viewport={'width':vp[0],'height':vp[1]}); errs=[]
            pg.on('pageerror',lambda e:errs.append(str(e)))
            await pg.route('**/fonts.g*',lambda r:r.abort())
            await pg.goto('http://localhost:8765/index.html#backtest'); await pg.wait_for_timeout(2500)
            fr=pg.frame_locator('#bt-frame')
            await fr.locator('#bBuy').click(); await fr.locator('#bStep').click()
            await fr.locator('#tools [data-tool="h"]').click()
            bb=await fr.locator('#chart').bounding_box(); await pg.mouse.click(bb['x']+bb['width']/2,bb['y']+bb['height']/2)
            f=[x for x in pg.frames if 'backtest.html' in x.url][0]
            print(vp, 'trades',await f.evaluate('trades.length'),'draws',await f.evaluate('X.draws.length'),'frame',await pg.evaluate('JSON.stringify(document.querySelector("#bt-frame").getBoundingClientRect())'),'ow',await pg.evaluate('document.documentElement.scrollWidth'),errs)
            await pg.screenshot(path=f's8_{vp[0]}.png')
        await b.close()
asyncio.run(main())
