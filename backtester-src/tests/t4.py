import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); ctx=await b.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
        pg=await ctx.new_page(); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1200)
        await pg.locator('#tools [data-tool="h"]').tap(); bb=await pg.locator('#chart').bounding_box()
        await pg.touchscreen.tap(bb['x']+200,bb['y']+250)
        await pg.locator('#tools [data-tool="r"]').tap(); await pg.touchscreen.tap(bb['x']+120,bb['y']+150); await pg.touchscreen.tap(bb['x']+260,bb['y']+220)
        print('touch draws',await pg.evaluate('X.draws.map(d=>d.type).join("")'),errs)
        await pg.screenshot(path='s9.png'); await b.close()
asyncio.run(main())
