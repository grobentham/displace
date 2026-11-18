import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1200)
        box=await pg.locator('#chart').bounding_box(); cx,cy=box['x'],box['y']
        await pg.evaluate('X.ict.fvg=true')
        await pg.keyboard.press('g'); await pg.mouse.click(cx+500,cy+330); await pg.mouse.click(cx+620,cy+150)
        await pg.mouse.click(cx+900,cy+450)
        await pg.evaluate('''(()=>{ $('#stopOnFill').checked=false; const ms=['Unicorn','OTE','Silver Bullet','']; for(let k=0;k<40;k++){ X.setup=ms[k%4]; submit(k%3?1:-1); advance(45+(k*7)%60,true); flatten(); advance(120,true);} pushUpdates(0); renderTick(); })()''')
        await pg.wait_for_timeout(300); await pg.screenshot(path='s5.png')
        await pg.click('#bExp'); await pg.click('#tabs button[data-p="anaPane"]'); await pg.wait_for_timeout(300); await pg.screenshot(path='s6.png')
        # phone
        pg2=await b.new_page(viewport={'width':390,'height':844}); pg2.on('pageerror',lambda e:errs.append('m:'+str(e)))
        await pg2.route('**/fonts.g*',lambda r:r.abort())
        await pg2.goto('http://localhost:8766/backtest.html'); await pg2.wait_for_timeout(1200)
        print('overflow',await pg2.evaluate('document.documentElement.scrollWidth'), await pg2.evaluate('JSON.stringify($("#chart").getBoundingClientRect())'))
        await pg2.screenshot(path='s7.png')
        print(errs); await b.close()
asyncio.run(main())
