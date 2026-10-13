import json, httpx
from playwright.sync_api import sync_playwright, expect
base='http://127.0.0.1:8001'
job=next(j for j in httpx.get(base+'/api/videos').json() if j['status']=='completed' and j.get('session_id'))
with sync_playwright() as p:
 browser=p.chromium.launch()
 page=browser.new_page(viewport={'width':1440,'height':1000})
 errors=[];writes=[]
 page.on('pageerror',lambda error:errors.append(str(error)))
 def no_writes(route):
  if route.request.method in ['PUT','POST','DELETE','PATCH']:
   writes.append(route.request.url);route.abort()
  else:route.continue_()
 page.route('**/api/**',no_writes)
 page.add_init_script("localStorage.setItem('fencecoach.session',"+json.dumps(job['session_id'])+");")
 page.goto(base+'/#coach',wait_until='networkidle')
 page.wait_for_selector('#replay-rep-picker')
 page.wait_for_function('!document.querySelector("#replay-rep-picker").disabled')
 box=page.locator('.coach-conversation-column').bounding_box(); video=page.locator('.coach-replay').bounding_box()
 assert box['x']+box['width']<=video['x']
 summary={'chatLeft':True,'videoRight':True,'nativeControls':page.locator('#replay-video').evaluate('(v)=>v.controls'),'frameButtons':page.locator('[data-frame-step]').count(),'repOptions':page.locator('#replay-rep-picker option').count()-1,'oldRepButtons':page.locator('[data-replay-time-jump]').count()}
 value=page.locator('#replay-rep-picker option').last.get_attribute('value')
 scroll=page.evaluate('scrollY')
 page.locator('#replay-rep-picker').select_option(value)
 assert abs(page.locator('#replay-video').evaluate('(v)=>v.currentTime')-float(value))<0.05
 summary['seekSeconds']=float(value);summary['seekPreservesScroll']=page.evaluate('scrollY')==scroll
 page.locator('.coach-model-control summary').click()
 expect(page.locator('.coach-settings-panel')).to_be_visible()
 summary['settingsDoNotReflow']=page.locator('.coach-replay').bounding_box()==video
 page.locator('.coach-model-control summary').click()
 page.evaluate('scrollTo(0,600)')
 page.wait_for_timeout(100)
 summary['videoStickyTop']=round(page.locator('.coach-replay').bounding_box()['y'],1)
 page.screenshot(path='work/coach-columns-desktop.png',full_page=True)
 page.set_viewport_size({'width':1024,'height':768})
 summary['laptopColumns']=page.locator('.coach-conversation-column').bounding_box()['x']<page.locator('.coach-replay').bounding_box()['x']
 page.set_viewport_size({'width':390,'height':844})
 page.evaluate('scrollTo(0,0)')
 summary['mobileOverflow']=page.evaluate('document.documentElement.scrollWidth > innerWidth')
 page.screenshot(path='work/coach-columns-mobile.png',full_page=True)
 page.set_viewport_size({'width':1440,'height':1000})
 page.evaluate('location.hash="review"')
 page.wait_for_selector('[data-review-rep-picker]')
 options=page.locator('[data-review-rep-picker] option').count()
 page.wait_for_function('Number.isFinite(document.querySelector("#replay-video").duration)')
 page.locator('#replay-video').evaluate('(v)=>window.reviewOriginalVideo=v')
 left=page.locator('.athlete-video-column').bounding_box();right=page.locator('.athlete-review-aside').bounding_box()
 assert left['x']+left['width']<=right['x']
 assert page.locator('.athlete-review-aside [data-review-rep-picker]').count()==1
 assert page.locator('.athlete-review-aside .athlete-rep-detail').count()==1
 assert page.locator('.athlete-video-column .athlete-rep-detail').count()==0
 page.locator('[data-review-rep-picker]').select_option(str(options-1))
 summary['reviewVideoLeftRepDetailsRight']=True
 summary['repSelectionKeepsVideo']=page.locator('#replay-video').evaluate('(v)=>v===window.reviewOriginalVideo')
 phase=page.locator('[data-review-phase-picker] option').last.get_attribute('value')
 page.locator('[data-review-phase-picker]').select_option(phase)
 assert abs(page.locator('#replay-video').evaluate('(v)=>v.currentTime')-float(phase)/1000)<0.05
 summary['phaseSeekSeconds']=float(phase)/1000
 page.screenshot(path='work/review-columns-desktop.png',full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 summary['reviewMobileOverflow']=page.evaluate('document.documentElement.scrollWidth > innerWidth')
 page.screenshot(path='work/review-columns-mobile.png',full_page=True)
 summary['reviewRepOptions']=options;summary['reviewSelected']=page.locator('[data-review-rep-picker]').input_value();summary['errors']=errors;summary['blockedWrites']=writes
 print(json.dumps(summary))
 browser.close()
