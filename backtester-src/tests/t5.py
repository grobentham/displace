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
            f=[x for x in pg.frames if 'backtest.html' in x.url][0]
            print(vp,'frame',await pg.evaluate('(()=>{const r=document.querySelector("#bt-frame").getBoundingClientRect();return [r.x,r.y,r.width,r.height,scrollY,document.documentElement.scrollWidth]})()'))
            await pg.screenshot(path=f'/tmp/bt2/s10_{vp[0]}.png')
            await f.click('#bFocus'); await f.wait_for_timeout(400); await f.click('#qBuy'); await f.click('#bStep')
            print(' focus chart',await f.evaluate('JSON.stringify([$("#chart").clientWidth,$("#chart").clientHeight,trades.length,$("#qPnl").textContent])'),errs)
            await pg.screenshot(path=f'/tmp/bt2/s11_{vp[0]}.png')
            # other routes still fine
            for h in ['tools','home','news']:
                await pg.goto('http://localhost:8765/index.html#'+h); await pg.wait_for_timeout(500)
            print(' other pages errs',errs)
        await b.close()
asyncio.run(main())
