import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1500); ev=pg.evaluate
        await ev("S.tilt=false; $('#stopOnFill').checked=false")
        await ev("""(()=>{ for(let k=0;k<24;k++){ $('#oQty').value=1+(k%3); submit(k%3?1:-1); advance(25+(k*7)%50,true); flatten(); advance(150,true);} pushUpdates(0); renderTick(); })()""")
        await pg.click('#tabs button[data-p="anaPane"]'); await pg.wait_for_timeout(300)
        print(await pg.evaluate("[...document.querySelectorAll('.anins')].map(e=>e.innerText).join('\\n---\\n')"))
        print((await pg.locator('#anaPane .an', has_text='Daily P&L calendar').inner_text())[:200].replace('\n',' '))
        print(errs); await b.close()
asyncio.run(main())
