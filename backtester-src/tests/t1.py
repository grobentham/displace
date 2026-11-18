import asyncio, json
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e))); pg.on('console',lambda m: errs.append('C:'+m.text) if m.type=='error' else None)
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1500)
        box=await pg.locator('#chart').bounding_box()
        cx,cy=box['x'],box['y']
        async def click(x,y): await pg.mouse.click(cx+x,cy+y)
        # drawings
        await pg.keyboard.press('h'); await click(400,150)
        await pg.keyboard.press('t'); await click(300,200); await pg.mouse.move(cx+500,cy+260); await click(500,260)
        await pg.keyboard.press('r'); await click(520,120); await click(640,180)
        await pg.keyboard.press('g'); await click(350,300); await click(450,180)
        await pg.keyboard.press('m'); await click(600,320); await click(700,220)
        print('draws',await pg.evaluate('X.draws.map(d=>d.type).join("")'),'sel',await pg.evaluate('X.sel'))
        # move the trend line by drag
        before=await pg.evaluate('JSON.stringify(X.draws[1])')
        await pg.mouse.move(cx+400,cy+230); await pg.mouse.down(); await pg.mouse.move(cx+420,cy+260,steps=5); await pg.mouse.up()
        after=await pg.evaluate('JSON.stringify(X.draws[1])'); print('moved',before!=after, await pg.evaluate('X.sel'))
        await pg.keyboard.press('Delete'); print('after del',await pg.evaluate('X.draws.length'))
        # pan still works?
        r0=await pg.evaluate('JSON.stringify(chart.timeScale().getVisibleLogicalRange())')
        await pg.mouse.move(cx+250,cy+420); await pg.mouse.down(); await pg.mouse.move(cx+350,cy+420,steps=5); await pg.mouse.up()
        print('pan ok',r0!=await pg.evaluate('JSON.stringify(chart.timeScale().getVisibleLogicalRange())'))
        # overlays on
        await pg.evaluate('X.ict.fvg=true'); await pg.wait_for_timeout(300)
        print('levels',await pg.evaluate('JSON.stringify(calcLevels())'))
        await pg.screenshot(path='/tmp/bt2/s1.png')
        # trading with tag, qty 4, partial
        await pg.select_option('#oSetup','Silver Bullet'); await pg.fill('#oQty','4')
        await pg.click('#bBuy'); await pg.keyboard.press('ArrowRight')
        await pg.click('#posPane button[data-a="half"]')
        print('pos qty',await pg.evaluate('trades[0].qty'),'closed',await pg.evaluate('JSON.stringify(closed.map(c=>[c.id,c.qty,c.model,c.sess,c.reason]))'))
        await pg.click('#bFlat')
        # many trades via engine for analytics
        await pg.evaluate('''(()=>{ $('#stopOnFill').checked=false; const ms=['Unicorn','OTE','Silver Bullet','']; for(let k=0;k<40;k++){ X.setup=ms[k%4]; submit(k%3?1:-1); advance(45+ (k*7)%60, true); flatten(); advance(120,true);} pushUpdates(0); renderTick(); })()''')
        print('closed n',await pg.evaluate('closed.length'), 'open',await pg.evaluate('trades.length'))
        await pg.evaluate('closeModal()'); await pg.click('#tabs button[data-p="anaPane"]'); await pg.wait_for_timeout(200)
        print('an tables',await pg.locator('#anaPane .an').count(), (await pg.locator('.anins').first.inner_text())[:200])
        await pg.click('#tabs button[data-p="histPane"]'); await pg.locator('#histPane select[data-f="grade"]').first.select_option('A')
        print('grade',await pg.evaluate('closed[closed.length-1].grade'))
        await pg.evaluate("document.querySelector('#bottom').style.height='520px'"); await pg.click('#tabs button[data-p="anaPane"]'); await pg.screenshot(path='/tmp/bt2/s2.png')
        # sessions save
        await pg.evaluate("document.querySelector('#bSess').click()"); await pg.fill('#ssName','Test A'); await pg.click('#ssSave'); print('sess',await pg.evaluate('sessList().length')); await pg.click('#mX')
        # challenge
        await pg.evaluate("document.querySelector('#bChal').click()"); await pg.select_option('#chPre','50'); await pg.locator('#mFoot .primary').click(); await pg.wait_for_timeout(200)
        print('ch',await pg.evaluate('JSON.stringify([S.chOn,X.ch,closed.length])'), await pg.locator('#chCard').inner_text())
        await pg.evaluate('''(()=>{ $('#oQty').value=40; $('#slOn').checked=false; $('#tpOn').checked=false; for(let k=0;k<30 && X.ch.state==='active';k++){ submit(1); advance(200,true); flatten(); } pushUpdates(0); renderTick(); })()''')
        print('ch after',await pg.evaluate('JSON.stringify([X.ch, acct().eq, trades.length])'), 'modal', await pg.locator('#mTitle').inner_text())
        await pg.screenshot(path='/tmp/bt2/s3.png'); await pg.locator('#mFoot button').first.click()
        await pg.click('#bBuy'); print('blocked',await pg.evaluate('trades.length'))
        # load saved session
        await pg.evaluate("document.querySelector('#bSess').click()"); await pg.click('#mBody button[data-a="load"]'); await pg.wait_for_timeout(300)
        print('loaded',await pg.evaluate('JSON.stringify([closed.length,S.chOn,X.draws.length,X.ch.state])'))
        # screenshot + skip + ICT modal
        await pg.evaluate("document.querySelector('#bShot').click()"); print('img',await pg.locator('#mBody img').count()); await pg.click('#mX')
        await pg.select_option('#skipSel','570'); print('clock',await pg.locator('#clock').inner_text())
        await pg.click('#bICT'); await pg.locator('#mFoot .primary').click()
        # reload persistence
        await pg.evaluate('saveNow()'); await pg.reload(); await pg.wait_for_timeout(1500)
        print('restored',await pg.evaluate('JSON.stringify([closed.length,X.draws.length,X.ict,closed[0].model])'))
        await pg.screenshot(path='/tmp/bt2/s4.png')
        print('ERRS',errs)
        await b.close()
asyncio.run(main())
