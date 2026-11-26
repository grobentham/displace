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
 await page.route('**/data/open/current.json*',route=>route.fulfill({json:{by_market:{nq:{n:0},es:{n:1},gold:{n:3}},
  forecasts:[{id:'f1',market:'nq',for:'2026-11-24',status:'verified_resolved',range_lo:456,range_hi:1328,actual_range:600,highTaken:1,lowTaken:0}]}}));
 await page.route('**/data/bias/current.json*',async route=>{
  const response=await route.fetch();
  const bias=await response.json();
  for (const [symbol, probability, direction] of [['nq',0.542,'long'],['es',0.477,'short'],['gold',0.506,'neutral']]) {
   Object.assign(bias.markets[symbol],{p_up:probability,base_up:probability,bias:direction,tier:'base'});
  }
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
 const snapshot=(symbol,time=day+'T09:55:00Z')=>({
  symbol,time,last:123.45,barTime:day+'T09:45:00Z',phaseText:'London fixture',lean:'bearish',
  leanText:symbol+' bearish fixture',lines:[symbol+' bearish fixture',symbol+' price line'],
  levels:{above:[{name:'Prior high',price:123.45}],below:[]}
 });
 let ironRequests=0;
 await page.route('https://raw.githubusercontent.com/grobentham/iron-brain/quotes/quotes.json*',route=>{
  ironRequests++;
  return route.fulfill({
   json:{outlook:{...snapshot('NQ'),markets:{es:snapshot('ES'),xauusd:{...snapshot('XAUUSD',day+'T09:00:00Z'),source:'xaus'}}}},
   headers:{'access-control-allow-origin':'*'}
  });
 });
 await page.goto(base+'index.html#top');
 const outlook=page.locator('.ib-outlook');
 await page.waitForFunction(()=>document.querySelector('#mc-pts').textContent==='776');
 assert.match(await page.locator('#mc-lean').innerText(),/Bullish lean.*Historical base rate.*54\.2%/);
 assert.equal(await outlook.isVisible(),false,'Iron Brain has its own page');
 assert.equal(ironRequests,0,'homepage does not fetch the Iron Brain feed');
 const biasTab=page.locator('#navlinks a[href="#intraday-bias"]');
 if (!await biasTab.isVisible()) await page.getByRole('button',{name:'Open menu'}).click();
 await biasTab.click();
 await page.waitForURL('**/index.html#intraday-bias');
 await outlook.getByText('NQ price line',{exact:true}).waitFor();
 assert.equal(await biasTab.getAttribute('aria-current'),'page');
 assert.deepEqual(await outlook.locator('[data-ib-market]').allTextContents(),['NQ','ES','XAUUSD']);
 assert.equal(await outlook.locator('.ib-outlook-lean strong').innerText(),'Bearish');
 assert.equal(await outlook.locator('.ib-outlook-price').innerText(),'123.45');
 assert.equal(await outlook.getByRole('heading',{name:'Nearby levels'}).count(),1);
 assert.equal(await outlook.locator('#ib-outlook-stamp time').getAttribute('datetime'),day+'T09:45:00Z');
 await outlook.getByRole('button',{name:'ES',exact:true}).click();
 assert.equal(await outlook.locator('.ib-outlook-lines').innerText(),'ES price line');
 await outlook.getByRole('button',{name:'XAUUSD',exact:true}).click();
 assert.equal(await outlook.locator('.ib-outlook-lines').innerText(),'XAUUSD price line');
 assert.equal(await outlook.locator('#ib-outlook-stamp [data-stale="true"]').innerText(),'Last available snapshot');
 assert.equal(await outlook.locator('.ib-outlook-unit').innerText(),'USD per troy ounce');
 assert.equal(await outlook.evaluate(el=>el.scrollWidth<=el.clientWidth),true,'Bias layout fits the viewport');
 assert.equal(await outlook.getByRole('link',{name:'XAUS indicative spot'}).getAttribute('href'),'https://xaus.com/api/');
 await outlook.getByRole('button',{name:'NQ',exact:true}).click();
 await page.reload();
 await outlook.getByText('NQ price line',{exact:true}).waitFor();
 assert.match(await page.title(),/^Bias · Displace$/);
 await page.getByRole('link',{name:'Displace',exact:true}).click();
 await page.waitForURL('**/index.html#top');
 await outlook.waitFor({state:'hidden'});
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
 assert.match(await page.locator('#mc-lean').innerText(),/Bearish lean.*47\.7%/);
 assert.equal(await page.locator('#mc-evidence').innerText(),'1 verified forecast scored');
 await page.getByRole('button',{name:'Share ES brief'}).click();
 assert.match(await page.locator('#mc-share-url').inputValue(),/sessions\/es\//);
 await page.getByRole('button',{name:'Share ES brief'}).click();
 await page.locator('#mc-t-gold').click();
 assert.match(await page.locator('#mc-lean').innerText(),/Neutral lean.*50\.6%/);
 await page.locator('#mc-t-nq').click();
 await page.getByRole('link',{name:'Review the last session'}).click();
 assert.match(await page.locator('#mc-review-results').innerText(),/600 points/);
 await page.getByLabel('One thing to carry into the next session').fill('Compare the next release window.');
 await page.getByRole('button',{name:'Save note on this device'}).click();
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
 assert(await page.getByRole('link',{name:'Subscribe to the high-impact calendar'}).isVisible());
 await page.reload();
 await page.waitForFunction(()=>document.querySelector('#mc-plan-status').textContent.includes('Saved plan loaded'));
 assert.equal(await page.locator('#mc-stop').inputValue(),'25');
 assert.equal(await page.locator('#mc-budget').inputValue(),'110');
 assert.equal(await page.locator('#mc-review-note').inputValue(),'Compare the next release window.');
 assert(await page.getByRole('link',{name:'Review my session plan'}).isVisible());
 await page.getByRole('button',{name:'Share MNQ brief'}).click();
 await page.getByRole('button',{name:'Copy link',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#mc-share-status').textContent.includes('copied'));
 const briefUrl=base+'mnq-brief.html?date='+day;
 const shareUrl=base+'sessions/nq/'+day+'.html';
 assert.equal(await page.locator('#mc-share-url').inputValue(),shareUrl);
 assert.equal(await page.evaluate(()=>window.copiedBriefUrl),shareUrl);
 const dims=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,inner:innerWidth}));
 assert(dims.scroll<=dims.inner+2,'home horizontal overflow at '+width+': '+JSON.stringify(dims));

 await page.locator('.navr .pillbtn').click();
 await page.waitForSelector('#bias-evidence',{state:'visible'});
 assert.equal(await page.locator('#bias-evidence').innerText(),'Live scoring pending');
 assert.equal(await page.locator('#bias-day .bq-top .bias-tag').innerText(),'Bullish lean');
 assert.equal(await page.locator('#bias-day .bq-n b').innerText(),'54.2%');
 assert.match(await page.locator('#bias-day .bias-why').first().innerText(),/Daily directional signal qualification is suspended/);
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
 await page.goto(base+'index.html#pro');
 const pro=page.locator('#pro');
 await pro.getByText('Historical market reactions',{exact:true}).waitFor();
 assert.equal(await pro.getByText('Direction engine',{exact:true}).count(),0);
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
    assert.equal(await page.locator('nav[aria-label="Site"] a[href="index.html#intraday-bias"]').count(),1,name+' Bias link');
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
