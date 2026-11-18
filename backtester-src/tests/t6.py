import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1500)
        ev=pg.evaluate
        c0=await ev('cur')
        # trade: market buy, step 3, limit order far, step; close; rewind checks
        await pg.click('#bBuy'); 
        for _ in range(3): await pg.keyboard.press('ArrowRight')
        await ev("otype='limit'"); await ev("$('#oPrice').value = fx(rt(lastPx()-2)); otype='limit'; submit(1); otype='market'")
        await ev("$('#stopOnFill').checked=false; advance(30)")
        print('after fwd', await ev('JSON.stringify([cur-%d,trades.length,orders.length,closed.length, trades.map(t=>t.src), closed.map(c=>c.reason)])'%c0))
        await ev('flatten(); advance(5)')
        print('flat', await ev('JSON.stringify([trades.length,closed.length])'))
        await ev('rewindTo(%d)'%(c0+2))
        print('rewound to +2', await ev('JSON.stringify([cur-%d,trades.length,orders.length,closed.length,trades.map(t=>[t.src,t.qty])])'%c0))
        await ev('rewindTo(%d)'%(c0+4))  # no-op (idx>cur clamps)
        await ev('jumpTo(%d)'%(c0+4))
        print('fwd +4', await ev('JSON.stringify([cur-%d,trades.length,orders.length,closed.length])'%c0))
        await pg.keyboard.press('ArrowLeft'); await pg.keyboard.press('Shift+ArrowLeft')
        print('keys back', await ev('cur-%d'%c0))
        await ev('rewindTo(%d)'%(c0-1)); print('before entry', await ev('JSON.stringify([trades.length,orders.length,closed.length])'))
        # speed keys, tf keys
        await pg.keyboard.press(']'); await pg.keyboard.press('4'); print('speed/tf',await ev('JSON.stringify([speed,tf])')); await pg.keyboard.press('3')
        # scrub
        await ev("(()=>{const s=$('#rScrub'); s.value=cur+500; s.dispatchEvent(new Event('input')); s.dispatchEvent(new Event('change'));})()")
        print('scrub', await ev('cur-%d'%c0), await pg.locator('#rDate').inner_text())
        # pause rules
        await ev("X.rp.open=true"); await ev("speed=500"); await pg.click('#bPlay'); await pg.wait_for_timeout(4000)
        print('paused at', await pg.locator('#clock').inner_text(), await ev('playing'))
        # second chart
        await pg.evaluate("document.querySelector('#bSplit').click()"); await pg.wait_for_timeout(500)
        print('c2', await ev('JSON.stringify([a2.length,a2cur===cur,X.c2, $("#chart").clientWidth, $("#c2").clientWidth])'))
        await pg.keyboard.press('ArrowRight'); await pg.wait_for_timeout(200); print('c2 sync',await ev('a2cur===cur'))
        await pg.select_option('#c2tf','900'); await pg.wait_for_timeout(300); print('c2 tf',await ev('JSON.stringify([a2.length,a2[a2.length-1].time-a2[a2.length-2].time])'))
        # drawing still maps on split
        await pg.keyboard.press('h'); bb=await pg.locator('#chart').bounding_box(); await pg.mouse.click(bb['x']+200,bb['y']+200); print('draw',await ev('X.draws.length'))
        await pg.screenshot(path='s12.png')
        await ev('saveNow()'); await pg.reload(); await pg.wait_for_timeout(1500); print('restored',await ev('JSON.stringify([X.c2,X.rp,a2.length>0])'))
        # challenge blocks rewind
        await ev("S.chOn=true; X.ch.state='active'; const c=cur; rewindTo(cur-5); window._d=c-cur"); print('challenge rewind moved',await ev('_d'))
        print('ERRS',errs); await b.close()
asyncio.run(main())
