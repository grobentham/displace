import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e))); pg.on('console',lambda m: errs.append('C:'+m.text) if m.type=='error' else None)
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1500); ev=pg.evaluate
        await ev("S.tilt=false; $('#stopOnFill').checked=false")
        # bulk trades incl. varied qty
        await ev("""(()=>{ const ms=['Unicorn','OTE','Silver Bullet','']; for(let k=0;k<30;k++){ X.setup=ms[k%4]; $('#oQty').value=1+(k%3); submit(k%3?1:-1); advance(25+(k*7)%50,true); flatten(); advance(150,true);} pushUpdates(0); renderTick(); })()""")
        print('closed', await ev('closed.length'))
        # scale-out test with synthetic bars
        await ev("""(()=>{ $('#scOn').checked=true; $('#scPts').value=5; $('#scPct').value=50; $('#oQty').value=4; $('#slOn').checked=true; $('#oSL').value=10; $('#tpOn').checked=false; const px=lastPx(); const tr=openTrade(1,4,px,D.t[cur],px-10,null,'t'); const i=cur+1; D.o[i]=px; D.h[i]=px+7; D.l[i]=px-1; D.c[i]=px+3; advance(1,true); window._so=[trades.map(t=>[t.qty,t.sl,px]), closed.slice(-1).map(c=>[c.qty,c.reason,c.exit])]; })()""")
        print('scale-out', await ev('JSON.stringify(_so)'))
        await ev('flatten()')
        # view trade
        await pg.click('#tabs button[data-p="histPane"]'); await ev("document.querySelector('#bottom').style.height='300px'")
        n=await pg.locator('#histPane button[data-v]').count(); print('view btns', n)
        await pg.locator('#histPane button[data-v]').nth(3).click(); await pg.wait_for_timeout(400)
        print('view', await ev('X.view && [X.view.id, X.view.side]'), await pg.locator('#banner').inner_text()); await pg.screenshot(path='s19.png')
        await pg.keyboard.press('Escape'); print('cleared', await ev('X.view'))
        # analytics
        await pg.click('#tabs button[data-p="anaPane"]'); await pg.wait_for_timeout(300)
        print('insights', (await pg.locator('.anins').first.inner_text())[:300].replace('\n',' | '))
        print('calendar', await pg.locator('#anaPane .an h4', has_text='Daily P&L calendar').count())
        await ev("document.querySelector('#bottom').style.height='700px'"); await ev("$('#anaPane').scrollTop=9999"); await pg.screenshot(path='s20.png')
        # rules
        await ev("S.maxTrades=1; S.dayLoss=0"); await ev("closed=[]; trades=[]"); await ev("submit(1)"); print('first ok', await ev('trades.length'))
        await ev("submit(1)"); print('blocked max', await ev('trades.length'), (await pg.locator('#toast').inner_text())[-90:].replace('\n',' '))
        await ev("S.maxTrades=0; flatten(); S.dayLoss=5; const px=lastPx(); const t=openTrade(-1,1,px,D.t[cur],null,null,'t'); closeTrade(t, px+10, D.t[cur], 'x');"); await ev("submit(1)"); print('blocked loss', await ev('trades.length'))
        await ev("S.dayLoss=0; S.kzOnly=true; jumpTo(idxAt(D.t[cur])+1)"); 
        await ev("(()=>{ let n=0; while(todMin(D.dt[cur])>=120&&todMin(D.dt[cur])<960&&n++<4000) advance(1,true); advance(1,true); })()")
        await ev("submit(1)"); print('kz-only outside', await ev('todMin(D.dt[cur])'), await ev('trades.length'))
        print('ERRS',errs); await b.close()
asyncio.run(main())
