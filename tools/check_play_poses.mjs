// Inspect the actual exported sidecar clips on the original textured models.
import { mkdir,writeFile } from 'node:fs/promises';
const { chromium }=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const out=process.argv[3] || 'pose-checks';await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader']});
const page=await browser.newPage({viewport:{width:1680,height:1050}}); const errors=[];
page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
try{
  await page.goto(process.argv[2] || 'http://127.0.0.1:5174');
  await page.waitForFunction(()=>window.render_game_to_text&&JSON.parse(window.render_game_to_text()).model);
  for(const [name,slug] of [['Red Dragon','dragon'],['Griffon V2','griffon']]){
    await page.getByRole('button',{name:new RegExp(`^${name} Updated`)}).click();
    await page.waitForFunction(name=>document.querySelector('#title').textContent===name&&!document.querySelector('#enter-play').disabled,name);
    await page.locator('#play').click(); await page.locator('#side').click();
    await page.locator('#grid').uncheck();
    for(const clip of ['Idle','Walk','Run','Turn Left','Turn Right','Takeoff','Flight','Glide','Bank Left','Bank Right','Land']){
      // search reveals full long lists without scrolling the transport off-screen
      await page.locator('#clip-filter').fill(`Play ${clip}`);
      await page.locator('#clips').getByRole('button',{name:`Play ${clip}`,exact:true}).click();
      const phases=['Walk','Run','Takeoff','Flight','Land'].includes(clip)?[.08,.4,.75]:[.4];
      for(const phase of phases){
        await page.locator('#timeline').fill(String(phase));await page.locator('#timeline').dispatchEvent('input');
        await page.evaluate(()=>window.advanceTime(1));
        await page.locator('#viewport canvas').screenshot({path:`${out}/${slug}-${clip.toLowerCase().replaceAll(' ','-')}-${phase}.png`});
      }
    }
  }
  await writeFile(`${out}/results.json`,JSON.stringify({errors,creatures:2,clips:22,renderedPoses:42},null,2));
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Rendered 42 exported poses across all 22 locomotion clips; no browser errors.');
}finally{await browser.close();}
