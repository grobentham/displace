import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e))); pg.on('console',lambda m: errs.append('C:'+m.text) if m.type=='error' else None)
        await pg.route('**/fonts.g*',lambda r:r.abort())
        await pg.goto('http://localhost:8766/backtest.html'); await pg.wait_for_timeout(1500); ev=pg.evaluate
        await ev("S.tilt=false")
        await pg.click('#bStrat'); await pg.wait_for_timeout(300)
        print('rules rows', await pg.locator('.stb .strow select[data-k^="c."]').count())
        # loosen rules so demo data fires
        for pre in ['Sweep + displacement in a kill zone','Opening range break','Trend pullback after a gap']:
            await pg.select_option('#stPre', pre); await pg.wait_for_timeout(100)
            await pg.click('text=Run test'); await pg.wait_for_timeout(1500)
            print(pre, await ev("SRES && [SRES.trades.length, SRES.sigs.length, SRES.bars]"))
        # both sides + simple rules
        await ev("ST=Object.assign(sdef(),{dir:'both',conds:[{t:'vwap'},{t:'brk',n:10}],maxDay:5}); stRender()")
        await pg.click('text=Run test'); await pg.wait_for_timeout(2000)
        print('both', await ev("[SRES.trades.length, SRES.trades.filter(t=>t.d>0).length, SRES.trades.filter(t=>t.d<0).length]"))
        print('result', (await pg.locator('#stRes .stgrid').inner_text())[:200].replace('\n',' '))
        # sanity: every trade pnl consistent, exits after entries, exit by valid
        print('sanity', await ev("SRES.trades.every(t=>t.xi>=t.e && isFinite(t.pnl)) && SRES.trades.every((t,i)=>i==0||t.e>SRES.trades[i-1].xi)"), await ev("[...new Set(SRES.trades.map(t=>t.why))].join(',')"))
        await pg.screenshot(path='s23.png')
        await pg.check('#stSigOn'); 
        await pg.locator('button[data-go]').nth(2).click(); await pg.wait_for_timeout(600)
        print('view', await ev("X.view && [X.view.side, X.view.reason]"), await ev("X.sigOn")); await pg.screenshot(path='s24.png')
        # save / load
        await pg.click('#bStrat'); await pg.fill('input[data-k="name"]','test one'); await pg.click('#stSaveBtn'); print('saved', await ev("stList().length"))
        # time rule + one-per-day cap
        await ev("ST=Object.assign(sdef(),{conds:[{t:'time',a:'09:30',b:'10:30'}],maxDay:1,exitAt:'15:55'}); stRender()"); await pg.click('text=Run test'); await pg.wait_for_timeout(1500)
        d=await ev("(()=>{const m={}; for(const t of SRES.trades){const k=Math.floor(D.dt[t.e]/86400); m[k]=(m[k]||0)+1;} return Math.max(...Object.values(m))})()")
        print('max/day', d, 'n', await ev("SRES.trades.length"))
        print('ERRS',errs); await b.close()
asyncio.run(main())
