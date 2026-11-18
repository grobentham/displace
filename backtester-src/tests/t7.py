import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1500)
        ev=pg.evaluate
        print(await ev("""(()=>{ $('#stopOnFill').checked=false; const c0=cur; $('#oPrice').value=fx(rt(lastPx()-3)); otype='limit'; submit(1); otype='market'; let n=0; while(!trades.length && !closed.length && n++<400) advance(1,true); const fillAt=cur-c0; advance(200,true); const st=[fillAt,trades.length,closed.length,orders.length]; rewindTo(c0+1); return JSON.stringify([st,[trades.length,closed.length,orders.length,orders[0]&&orders[0].type]]); })()"""))
        await ev("advance(400)"); print('refill',await ev('JSON.stringify([trades.length+closed.length,orders.length])'))
        print(errs); await b.close()
asyncio.run(main())
