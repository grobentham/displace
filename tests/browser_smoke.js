'use strict';
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base='http://127.0.0.1:8765/';
const pages=['terminal','macro','signals','relationships','atlas','research','research-v2','publications','open','search'];
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const width of [1366,390]){
   const context=await browser.newContext({viewport:{width,height:900}});
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
    if(name==='terminal')await page.waitForFunction(()=>/10 \/ 10 panels loaded/.test(document.querySelector('#load-status').textContent));
    if(name==='atlas'){
     await page.waitForSelector('#country option[value="SGP"]');
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
