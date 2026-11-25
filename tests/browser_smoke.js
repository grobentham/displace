'use strict';
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8765/';
const pages=['research-hub','macro','signals','relationships','atlas','research','research-v2','research-v3','publications','open','search','validation'];
async function checkOutlook(page, width) {
 const day='2026-11-25';
 let sessionDay=day;
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
  bias.for=sessionDay;
  bias.markets.nq.range.points=775.926804;
  bias.markets.nq.session={date:sessionDay,open:'2026-11-24T18:00:00-05:00',close:'2026-11-25T17:00:00-05:00',halts:[]};
  await route.fulfill({response,json:bias});
 });
 await page.route('**/data/briefs/mnq/'+day+'.json',route=>route.fulfill({json:{
  date:day,asof:day+'T09:00:00Z',session:{},range:{points:775.926804,lo:456,hi:1328},live_count:0,
  levels:{high:{price:26350.75,probability:0.64},low:{price:25905.25,probability:0.73}},
  news:[{title:'Beige Book fixture',instant:day+'T19:00:00Z',time_ny:'14:00',impact:'medium'}]
 }}));
 await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{
  configurable:true,value:{writeText:async url=>{window.copiedBriefUrl=url;}}
 }));
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
 await page.getByRole('link',{name:'Plan my session',exact:true}).click();
 await page.waitForURL('**/index.html#session-plan');
 await page.locator('#mc-allowance').fill('250');
 await page.locator('#mc-budget').fill('110');
 await page.locator('#mc-stop').fill('25');
 await page.locator('#mc-qty').fill('3');
 await page.locator('#mc-cost').fill('2.50');
 assert.equal(await page.locator('#mc-result-unit').innerText(),'$52.50');
 assert.equal(await page.locator('#mc-result-max').innerText(),'2');
 assert.equal(await page.locator('#mc-result-total').innerText(),'$157.50');
 assert.equal(await page.locator('#mc-result-left').innerText(),'$92.50');
 assert.match(await page.locator('#mc-plan-fit').innerText(),/exceeds/);
 await page.locator('#mc-allowance').fill('0');
 assert.equal(await page.locator('#mc-result-max').innerText(),'0');
 assert.equal(await page.locator('#mc-result-left').innerText(),'-$157.50');
 await page.locator('#mc-allowance').fill('250');
 await page.locator('#mc-qty').fill('2');
 assert.match(await page.locator('#mc-plan-fit').innerText(),/fits/);
 await page.getByRole('button',{name:'Save session plan'}).click();
 assert.match(await page.locator('#mc-plan-status').innerText(),/Plan saved on this device/);
 await page.reload();
 await page.waitForFunction(()=>document.querySelector('#mc-plan-status').textContent.includes('Saved plan loaded'));
 assert.equal(await page.locator('#mc-stop').inputValue(),'25');
 assert.equal(await page.locator('#mc-budget').inputValue(),'110');
 await page.getByRole('button',{name:'Share MNQ brief'}).click();
 await page.getByRole('button',{name:'Copy link',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#mc-share-status').textContent.includes('copied'));
 const briefUrl=base+'mnq-brief.html?date='+day;
 assert.equal(await page.locator('#mc-share-url').inputValue(),briefUrl);
 assert.equal(await page.evaluate(()=>window.copiedBriefUrl),briefUrl);
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

 sessionDay='2026-11-27';
 await page.goto(briefUrl);
 await page.waitForSelector('#brief-content',{state:'visible'});
 assert.match(await page.locator('#brief-date').innerText(),/November 25/);
 assert.equal(await page.locator('#brief-range').innerText(),'776');
 assert.match(await page.locator('#brief-news time').innerText(),/Thu, Nov 26.*3:00 AM/);
 assert.equal(await page.locator('#mc-plan-form,input').count(),0);
 const publicDims=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,inner:innerWidth}));
 assert(publicDims.scroll<=publicDims.inner+2,'brief horizontal overflow at '+width+': '+JSON.stringify(publicDims));
 await page.getByRole('link',{name:'Plan my session',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#mc-plan-session').textContent.includes('Nov 27'));
 assert.equal(await page.locator('#mc-allowance').inputValue(),'');
 assert.equal(await page.locator('#mc-stop').inputValue(),'');
 assert.equal(await page.locator('#mc-budget').inputValue(),'110');
 assert.equal(await page.locator('#mc-cost').inputValue(),'2.50');
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
