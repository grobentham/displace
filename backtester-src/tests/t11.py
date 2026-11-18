import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e))); pg.on('console',lambda m: errs.append('C:'+m.text) if m.type=='error' else None)
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1500); ev=pg.evaluate
        # indicators: hide EMA fast, remove, add custom
        await pg.click('#tInd'); print('modal', await pg.locator('#mTitle').inner_text(), await pg.locator('#mBody .irow').count())
        await pg.locator('#mBody input[data-b="e1"]').uncheck(); print('hideE1', await ev('S.hideE1'), await ev('ema1S.data().length'))
        for t in ['sma','bb','rsi','ema']:
            await pg.select_option('#iaT',t); await pg.click('#iaGo'); await pg.wait_for_timeout(200)
        print('inds', await ev('JSON.stringify(X.inds.map(i=>[i.type,i.len,i.on,(i.v||[]).filter(Boolean).length]))'))
        await ev("advance(40)"); await pg.wait_for_timeout(300)
        print('after play', await ev('JSON.stringify(X.inds.map(i=>[i.type,i.ser.map(s=>s.data().length)]))'))
        print('rsi sample', await ev('X.inds.find(i=>i.type==="rsi").v.filter(Boolean).slice(-3).map(p=>p.value.toFixed(1)).join(",")'))
        print('legend', (await pg.locator('#ind').inner_text())[:140])
        await pg.screenshot(path='s17.png')
        # remove one, toggle off
        await pg.locator('#mBody button[data-f="rm"]').first.click(); print('after rm', await ev('X.inds.length'))
        await pg.locator('#mBody input[data-f="on"]').first.uncheck(); print('off', await ev('X.inds[0].on'))
        await pg.fill('#mBody input[data-f="len"]>>nth=0','30'); await pg.locator('#mBody input[data-f="len"]').first.dispatch_event('change'); print('len', await ev('X.inds[0].len'))
        await pg.locator('#mFoot .primary').click()
        await ev('saveNow()'); await pg.reload(); await pg.wait_for_timeout(1500)
        print('restored inds', await ev('JSON.stringify(X.inds.map(i=>[i.type,i.len,i.on,i.ser?i.ser[0].data().length:-1]))'), await ev('S.hideE1'))
        # tf switch + rewind keep working
        await pg.keyboard.press('4'); await pg.wait_for_timeout(300); await ev('rewindTo(cur-30)'); await ev('advance(20)'); print('tf/rewind ok', await ev('tf'))
        # context menu orders
        await pg.keyboard.press('3')
        bb=await pg.locator('#chart').bounding_box(); lp=await ev('lastPx()'); y=await ev('candle.priceToCoordinate(lastPx()-15)')
        await pg.mouse.click(bb['x']+400,bb['y']+y,button='right'); await pg.wait_for_timeout(200)
        print('menu', (await pg.locator('#ctx').inner_text()).replace('\n',' | ')); await pg.screenshot(path='s18.png')
        await pg.locator('#ctx button[data-k="0"]').click(); print('order', await ev('JSON.stringify(orders.map(o=>[o.type,o.side,o.price,o.sl,o.tp]))'), await ev('lastPx()'))
        y2=await ev('candle.priceToCoordinate(lastPx()+10)')
        await pg.mouse.click(bb['x']+400,bb['y']+y2,button='right'); await pg.locator('#ctx button[data-k="1"]').click(); print('orders', await ev('JSON.stringify(orders.map(o=>[o.type,o.side]))'))
        await pg.mouse.click(bb['x']+400,bb['y']+y2,button='right'); await pg.locator('#ctx button[data-a="line"]').click(); print('line', await ev('X.draws.length'))
        # gate + ctx
        await ev("orders=[]; S.gate=true; X.setup='OTE'"); await pg.mouse.click(bb['x']+400,bb['y']+y,button='right'); await pg.locator('#ctx button[data-k="0"]').click(); print('gate', await pg.locator('#mTitle').inner_text())
        await pg.locator('#mFoot button').nth(1).click(); print('skipped limit', await ev('JSON.stringify(orders.map(o=>[o.type,o.rules]))')); await ev('S.gate=false')
        # url load
        open('/tmp/bt2/c.csv','w').write("time,open,high,low,close,Volume\n"+"\n".join(f"{1790000000+60*i},{21000+i%9},{21004+i%9},{20997+i%9},{21002+i%9},{50+i}" for i in range(2000)))
        await pg.evaluate("document.querySelector('#bData').click()"); await pg.fill('#urlIn','http://localhost:8766/c.csv'); await pg.click('#urlGo'); await pg.wait_for_timeout(800)
        print('url', await ev('JSON.stringify([D.name,D.n])'))
        await pg.evaluate("document.querySelector('#bData').click()"); await pg.fill('#urlIn','https://github.com/u/r/blob/main/x.csv'); await pg.click('#urlGo'); await pg.wait_for_timeout(1500); print('blocked msg', (await pg.locator('#loadMsg').inner_text())[:100])
        print('ERRS',errs); await b.close()
asyncio.run(main())
