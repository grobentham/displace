'use strict';
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8765/';
const pages=['research-hub','macro','signals','relationships','atlas','research','research-v2','research-v3','publications','open','search','validation'];
async function checkOutlook(page, width) {
 const day='2026-11-25';
 const news=[
  {id:'fixture-gdp',date:day,time:'08:30',impact:'high',cur:'USD',title:'GDP fixture',src:'Fixture'},
  {id:'fixture-beige',date:day,time:'14:00',impact:'medium',cur:'USD',title:'Beige Book fixture',src:'Fixture'}
 ];
 await page.clock.setFixedTime(new Date(day+'T10:00:00Z'));
 await page.route('**/data/calendar/events.json*',route=>route.fulfill({json:{updated:'2099-01-01',through:day,events:news}}));
 await page.route('**/data/open/current.json*',route=>route.fulfill({json:{by_market:{nq:{n:0},es:{n:1},gold:{n:3}}}}));
 await page.route('**/data/bias/current.json*',async route=>{
  const response=await route.fetch();
  const bias=await response.json();
  bias.for=day;
  bias.markets.nq.range.points=775.926804;
  bias.markets.nq.session={date:day,open:'2026-11-24T18:00:00-05:00',close:'2026-11-25T17:00:00-05:00',halts:[]};
  await route.fulfill({response,json:bias});
 });
 await page.goto(base+'index.html#top');
 await page.waitForFunction(()=>document.querySelector('#mc-pts').textContent==='776');
 await page.waitForFunction(()=>document.querySelector('#mc-evidence').textContent==='Live scoring pending');
 assert.match(await page.locator('#mc-window').innerText(),/Nov 24, 18:00.*Nov 25, 17:00 New York/);
 assert.match(await page.locator('#mc-news .mc-row').filter({hasText:'Beige Book fixture'}).innerText(),/Thu, Nov 26/);
 assert.equal(await page.locator('#jform,#nbar').count(),0);
 assert(await page.locator('#jfree').isVisible(),'no-account entry card');
 const reminder=page.locator('#mc-news + .mc-news-actions button');
 await reminder.click();
 assert.equal(await reminder.getAttribute('aria-pressed'),'true');
 assert.match(await reminder.getAttribute('aria-label'),/GDP fixture/);
 await reminder.click();
 assert.equal(await reminder.getAttribute('aria-pressed'),'false');
 await page.locator('#mc-t-es').click();
 assert.equal(await page.locator('#mc-evidence').innerText(),'1 verified forecast scored');
 await page.locator('#mc-t-nq').click();
 const dims=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,inner:innerWidth}));
 assert(dims.scroll<=dims.inner+2,'home horizontal overflow at '+width+': '+JSON.stringify(dims));

 await page.locator('.navr .pillbtn').click();
 await page.waitForSelector('#bias-evidence',{state:'visible'});
 assert.equal(await page.locator('#bias-evidence').innerText(),'Live scoring pending');
 assert.equal(await page.locator('.bo-t tr[data-go="nq"] td:nth-child(4)').innerText(),'776 pts');
 assert(await page.getByRole('heading',{name:'Historical scorecard'}).isVisible());
 await page.goto(base+'index.html#calendar');
 const overnight=page.locator('.nx-c').filter({hasText:'Beige Book fixture'});
 await overnight.waitFor();
 assert.equal(await overnight.locator('.nx-d b').innerText(),'26');
}

(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const width of [1366,390]){
   const context=await browser.newContext({viewport:{width,height:900},timezoneId:'Asia/Singapore',locale:'en-US'});
   await context.route('**/*',route=>route.request().url().startsWith(base)?route.continue():route.abort());
   const page=await context.newPage();
   const errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   for(const name of pages){
    const response=await page.goto(base+name+'.html',{waitUntil:'networkidle'});
    assert.equal(response.status(),200,name);
    assert(await page.locator('h1').first().isVisible(),name+' heading');
    const dims=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,inner:innerWidth}));
    assert(dims.scroll<=dims.inner+2,name+' horizontal overflow at '+width+': '+JSON.stringify(dims));
    if(name==='atlas'){
     await page.waitForSelector('#country option[value="SGP"]',{state:'attached'});
     await page.selectOption('#country','USA');
     await page.waitForFunction(()=>document.querySelector('#profile-note').textContent.includes('United States'));
    }
    if(name==='search'){
     await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('2/2'));
     await page.fill('#q','Singapore');
     assert(await page.locator('#results a[href="atlas.html?country=SGP"]').isVisible(),'country search');
     await page.locator('#results a[href="atlas.html?country=SGP"]').click();
     await page.waitForFunction(()=>document.querySelector('#country').value==='SGP');
    }
   }
   await checkOutlook(page,width);
   assert.deepEqual(errors,[],'uncaught page errors at '+width);
   await context.close();
  }
  const context=await browser.newContext();
  const page=await context.newPage();
  await page.goto(base+'publications.html',{waitUntil:'networkidle'});
  const article=page.locator('#article a').filter({hasText:'Permanent article'});
  await article.waitFor();
  await article.click();
  assert(await page.locator('main h1').isVisible(),'static report heading');
  assert(await page.locator('link[rel=canonical]').count()===1,'static article canonical');
  await context.close();
 }finally{await browser.close()}
 console.log('desktop/mobile intelligence smoke tests passed');
})().catch(e=>{console.error(e);process.exitCode=1});
