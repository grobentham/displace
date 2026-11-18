import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e))); pg.on('console',lambda m: errs.append('C:'+m.text) if m.type=='error' else None)
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1500)
        ev=pg.evaluate
        # --- drills
        await pg.evaluate("document.querySelector('#bDrill').click()"); await pg.select_option('#drM','Silver Bullet'); await pg.locator('#mFoot .primary').click(); await pg.wait_for_timeout(400)
        print('drill', await ev('JSON.stringify([X.dr,X.setup,X.drillInfo&&X.drillInfo.model,X.drillEnd-cur])'), await pg.locator('#clock').inner_text(), await pg.locator('#rDrill').inner_text())
        await ev("$('#stopOnFill').checked=false; submit(1); advance(6)")
        print('trade tagged',await ev('JSON.stringify(trades.map(t=>[t.model,t.dr,t.rules]))'))
        await ev("speed=500"); await pg.click('#bPlay'); await pg.wait_for_timeout(2500)
        print('review modal', await pg.locator('#mTitle').inner_text(), 'playing',await ev('playing'))
        await pg.screenshot(path='s14.png')
        await pg.locator('#mFoot .primary').click(); await pg.wait_for_timeout(300)
        print('second drill', await ev('JSON.stringify([X.dr,closed.length,trades.length])'))
        # rewind inside drill only touches drill trades
        await ev("submit(1); advance(10,true); flatten()"); await ev('rewindTo(cur-12)')
        print('rewind', await ev('JSON.stringify([closed.map(c=>c.dr),trades.length])'))
        # --- checklist gate
        await ev("S.gate=true; X.setup='OTE'"); await pg.click('#bBuy'); print('gate title', await pg.locator('#mTitle').inner_text(), await pg.locator('#mBody input[data-ck]').count())
        await pg.locator('#mFoot .primary').click(); print('still open (unticked)', await pg.locator('#mTitle').inner_text())
        for i in range(5): await pg.locator('#mBody input[data-ck]').nth(i).check()
        await pg.locator('#mFoot .primary').click(); print('placed', await ev('JSON.stringify(trades.map(t=>t.rules))'))
        await ev('flatten()'); 
        await pg.click('#bSell'); await pg.locator('#mFoot button').nth(1).click(); print('skipped', await ev('JSON.stringify(trades.map(t=>t.rules))'))
        await ev('flatten(); S.gate=false')
        # --- tilt: force 3 losses
        await ev("""(()=>{ X.tiltShown=0; for(let k=0;k<3;k++){ $('#slOn').checked=true; $('#oSL').value=2; $('#tpOn').checked=false; const px=lastPx(); openTrade(1,1,px,D.t[cur],px-2,null,'t'); closeTrade(trades[0], px-2, D.t[cur], 'Stop'); } })()""")
        print('tilt', await pg.locator('#mTitle').inner_text()); await pg.locator('#mFoot .primary').click(); await pg.wait_for_timeout(500); await pg.click('#bBuy')
        print('cool banner', await pg.locator('#banner').inner_text(), 'trades',await ev('trades.length'))
        await ev('X.cool=0; banner("")')
        # --- BE + trail via engine
        await ev("S.beR=1; S.trailPts=0; closeModal(); const px=lastPx(); const tr=openTrade(1,1,px,D.t[cur],px-4,null,'t'); const i=cur+1; D.o[i]=px; D.c[i]=px+5; D.h[i]=px+9; D.l[i]=px-1; advance(1,true); window._sl=[tr.sl,px,trades.length]")
        print('BE', await ev('JSON.stringify(_sl)'))
        await ev('flatten()')
        # --- levels
        await ev("X.ict.rng=true; X.ict.pw=true; X.ict.orb=true; X.ict.eq=true; jumpTo(idxAt(D.t[cur])+300); X.lvC=null"); await pg.wait_for_timeout(400)
        print('levels', await ev('JSON.stringify(calcLevels())'))
        await pg.screenshot(path='s15.png')
        # --- analytics split
        await ev("closeModal(); S.tilt=false"); await ev("for(let k=0;k<6;k++){ X.setup='OTE'; X.rulesNext=k%2?'followed':'skipped'; submit(1); advance(30,true); flatten(); } X.rulesNext=''; X.an=-1"); 
        await pg.click('#tabs button[data-p="anaPane"]'); print('checklist table', await pg.locator('#anaPane .an h4', has_text='By checklist').count(), await pg.locator('#anaPane .an h4', has_text='By re-entry').count())
        # --- settings
        await pg.click('#bSettings'); print('settings fields', await pg.locator('#mBody [data-k="newsSlip"]').count(), await pg.locator('#mBody [data-k="limThru"]').count()); await pg.fill('#mBody [data-k="trailPts"]','5'); await pg.locator('#mBody [data-k="limThru"]').check(); await pg.locator('#mFoot .primary').click(); print('S',await ev('JSON.stringify([S.trailPts,S.limThru])'))
        # --- sessions export/import + library
        await pg.evaluate("document.querySelector('#bSess').click()"); await pg.fill('#ssName','x'); await pg.click('#ssSave'); print('exp btn', await pg.locator('#ssExp').count()); await pg.click('#mX')
        # multi-file csv
        import time
        rows=lambda a,b:"time,open,high,low,close,Volume\n"+"\n".join(f"{1790000000+60*i},{21000+i%7},{21003+i%7},{20998+i%7},{21001+i%7},{100+i}" for i in range(a,b))
        open('/tmp/bt2/a.csv','w').write(rows(0,1500)); open('/tmp/bt2/b.csv','w').write(rows(1200,3000))
        await pg.evaluate("document.querySelector('#bData').click()"); await pg.locator('#fileIn').set_input_files(['/tmp/bt2/a.csv','/tmp/bt2/b.csv']); await pg.wait_for_timeout(800)
        print('stitched', await ev('JSON.stringify([D.name,D.n])'), await ev('libMeta().length'))
        await ev('loadDemo()'); await pg.wait_for_timeout(300)
        await pg.evaluate("document.querySelector('#bData').click()"); print('lib rows', await pg.locator('#mBody button[data-l="load"]').count()); await pg.locator('#mBody button[data-l="load"]').first.click(); await pg.wait_for_timeout(600)
        print('from library', await ev('D.n'))
        print('ERRS',errs); await b.close()
asyncio.run(main())
