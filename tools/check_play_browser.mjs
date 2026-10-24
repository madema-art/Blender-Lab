// Run with PLAYWRIGHT_MODULE pointing to a local Playwright ESM entry if needed.
import assert from 'node:assert/strict';
import { mkdir,writeFile } from 'node:fs/promises';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const url=process.argv[2] || 'http://127.0.0.1:5174';
const output=process.argv[3] || 'play-checks'; await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:900}}); const errors=[],warnings=[],results=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text());if(m.type()==='warning')warnings.push(m.text());});
const state=()=>page.evaluate(()=>JSON.parse(window.render_game_to_text()));
const step=async(ms=1000)=>page.evaluate(ms=>window.advanceTime(ms),ms);
const key=async(code,ms)=>{await page.keyboard.down(code);await step(ms);await page.keyboard.up(code);};
const shot=name=>page.screenshot({path:`${output}/${name}.png`});
try{
  await page.goto(url);await page.waitForFunction(()=>window.render_game_to_text&&JSON.parse(window.render_game_to_text()).model);
  for(const [name,slug] of [['Red Dragon','dragon'],['Griffon V2','griffon']]){
    await page.getByRole('button',{name:new RegExp(`^${name} Updated`)}).click();
    await page.waitForFunction(name=>document.querySelector('#title').textContent===name&&document.querySelector('#enter-play').disabled===false,name);
    await page.locator('#play').click(); // viewer paused state must survive
    await page.locator('#timeline').fill('0.3');await page.locator('#timeline').dispatchEvent('input');
    const saved=await page.locator('#timeline').inputValue();
    await shot(`${slug}-viewer`);
    await page.locator('#enter-play').click();await step(700);
    assert.equal((await state()).mode,'play');assert.equal(await page.locator('.inspector').isVisible(),false);
    await shot(`${slug}-idle`);
    await key('w',1200);assert.equal((await state()).state,'walk');await shot(`${slug}-walk`);
    await page.keyboard.down('w');await key('Shift',1600);assert.equal((await state()).state,'run');await shot(`${slug}-run`);await page.keyboard.up('w');
    await key('Space',650);assert.equal((await state()).state,'takeoff');await shot(`${slug}-takeoff`);
    await step(3500);assert.equal((await state()).state,'flight');
    await page.keyboard.down('w');await key('e',1400);await key('a',300);await shot(`${slug}-bank`);await page.keyboard.up('w');
    const altitude=(await state()).position[1];assert.ok(altitude>3);
    await page.keyboard.down('g');await step(500);assert.equal((await state()).state,'glide');await shot(`${slug}-glide`);await page.keyboard.up('g');
    const camera=(await state()).camera;
    await page.mouse.move(700,450);await page.mouse.down();await page.mouse.move(920,510,{steps:10});await page.mouse.up();await page.mouse.wheel(0,-150);await step(500);
    assert.notDeepEqual((await state()).camera,camera);
    await key('q',800);assert.ok((await state()).position[1]<altitude);
    await key('l',500);assert.equal((await state()).state,'land');await shot(`${slug}-land`);
    await step(9000);assert.equal((await state()).state,'idle');assert.equal((await state()).position[1],0);
    if(slug==='dragon'){await key('r',1500);assert.equal((await state()).special,'roar');await shot('dragon-roar');await step(4500);}
    // Standard Gamepad API shape, simulated in this isolated browser only.
    await page.evaluate(()=>{window.testPad={connected:true,mapping:'standard',axes:[.5,-.8,.4,0],buttons:Array.from({length:16},()=>({value:0,pressed:false}))};Object.defineProperty(navigator,'getGamepads',{configurable:true,value:()=>[window.testPad]});});
    const before=(await state()).position;await step(1500);assert.notDeepEqual((await state()).position,before);
    await page.evaluate(()=>{testPad.buttons[0].value=1;});await step(300);assert.equal((await state()).state,'takeoff');
    await page.evaluate(()=>{testPad.buttons[0].value=0;testPad.axes=[0,0,0,0];});await step(4000);
    const padHeight=(await state()).position[1];
    await page.evaluate(()=>{testPad.buttons[7].value=.8;});await step(1000);assert.ok((await state()).position[1]>padHeight);
    await page.evaluate(()=>{testPad.buttons[7].value=0;testPad.buttons[6].value=.8;});await step(2000);assert.ok((await state()).position[1]<padHeight);
    await page.evaluate(()=>{testPad.buttons[6].value=0;});
    await page.evaluate(()=>{testPad.buttons[3].value=1;});await step(100);assert.equal((await state()).state,'glide');
    await page.evaluate(()=>{testPad.buttons[3].value=0;testPad.buttons[1].value=1;});await step(100);assert.equal((await state()).state,'land');
    await page.evaluate(()=>{testPad.buttons[1].value=0;});await step(9000);
    if(slug==='dragon'){
      await page.evaluate(()=>{testPad.buttons[2].value=1;});await step(300);assert.equal((await state()).special,'roar');
      await page.evaluate(()=>{testPad.buttons[2].value=0;});await step(4500);
    }
    await page.evaluate(()=>{testPad.buttons[9].value=1;});await step(100);assert.equal((await state()).mode,'viewer');
    await page.evaluate(()=>{testPad=null;});
    assert.equal(await page.locator('#timeline').inputValue(),saved);
    assert.equal(await page.locator('#play').getAttribute('aria-label'),'Play animation');
    const baseline=(await state()).resources;
    for(let i=0;i<8;i++){await page.locator('#enter-play').click();await step(100);await page.keyboard.press('Escape');assert.equal((await state()).mode,'viewer');}
    assert.ok((await state()).resources.geometries<=baseline.geometries+2,'repeated switching must release playground geometry');
    assert.ok((await state()).resources.textures<=baseline.textures+2,'repeated switching must release shadow textures');
    await shot(`${slug}-restored`);results.push(`${name}: viewer restore, walk/run, takeoff/flight/bank/glide/land, mouse orbit/zoom, simulated Xbox and 8 repeated switches passed`);
  }
  await page.getByRole('button',{name:/^Glowing Glass Cube Updated/}).click();await page.waitForFunction(()=>document.querySelector('#title').textContent==='Glowing Glass Cube');
  assert.equal(await page.locator('#enter-play').isDisabled(),true);
  assert.match(await page.locator('#play-readiness').textContent(),/No creature capability profile/);
  results.push('Static creation remains inspectable and Play Mode explains missing profile');
  assert.deepEqual(errors,[]);assert.equal(warnings.filter(x=>/No target node|binding/i.test(x)).length,0);
  await writeFile(`${output}/results.json`,JSON.stringify({results,errors,warnings},null,2));
  console.log(JSON.stringify({results,errors,warnings},null,2));
}finally{await browser.close();}
