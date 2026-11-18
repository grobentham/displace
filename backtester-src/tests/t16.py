import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':900}); errs=[]
        pg.on('pageerror',lambda e:errs.append(str(e))); pg.on('console',lambda m: errs.append('C:'+m.text) if m.type=='error' else None)
        await pg.route('**/fonts.g*',lambda r:r.abort()); await pg.route('**/*.{mp3}',lambda r:r.abort())
        await pg.goto('http://localhost:8765/index.html#calendar'); await pg.wait_for_timeout(1500)
        print('chips', await pg.locator('#ec-imp .ecchip').all_inner_texts())
        await pg.evaluate("document.querySelector('#ec-range [data-v=\"all\"]')&&document.querySelector('#ec-range [data-v=\"all\"]').click()"); await pg.wait_for_timeout(300)
        n=await pg.locator('.ecrow.i-earnings').count(); print('earnings rows', n)
        print(await pg.locator('.ecrow.i-earnings').first.inner_text())
        await pg.locator('.ecrow.i-earnings .ecmain').first.click(); await pg.wait_for_timeout(300)
        await pg.screenshot(path='/tmp/bt2/s26.png')
        await pg.click('#ec-imp [data-imp="earnings"]'); await pg.wait_for_timeout(200)
        print('after toggle', await pg.locator('.ecrow.i-earnings').count())
        print(errs); await b.close()
asyncio.run(main())
