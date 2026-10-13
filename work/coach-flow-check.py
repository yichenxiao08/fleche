import json,httpx
from playwright.sync_api import sync_playwright
base='http://127.0.0.1:8001'
job=next(j for j in httpx.get(base+'/api/videos').json() if j['status']=='completed' and j.get('session_id'))
with sync_playwright() as p:
 browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
 errors=[];writes=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 def api_guard(route):
  if route.request.method not in ['GET','HEAD']:writes.append(route.request.url);route.abort()
  else:route.continue_()
 page.route('**/api/**',api_guard)
 page.add_init_script("localStorage.setItem('fencecoach.session',"+json.dumps(job['session_id'])+");")
 page.goto(base+'/#coach',wait_until='networkidle')
 page.wait_for_selector('.coach-composer')
 top=page.locator('.coach-composer').bounding_box()['y']
 page.evaluate('scrollTo(0,700)');page.wait_for_timeout(50)
 after=page.locator('.coach-composer').bounding_box()['y']
 assert abs((top-after)-700)<1
 scroll=page.evaluate('scrollY')
 page.evaluate('document.querySelector("button[data-question]").click()')
 assert page.evaluate('scrollY')==scroll
 summary={'composerPosition':page.locator('.coach-composer').evaluate('(e)=>getComputedStyle(e).position'),'composerScrollsWithDocument':True,'suggestionFocusPreservesScroll':True,'videoStickyTop':page.locator('.coach-replay').bounding_box()['y'],'chatLeft':page.locator('.coach-conversation-column').bounding_box()['x']<page.locator('.coach-replay').bounding_box()['x'],'writes':writes,'errors':errors}
 page.evaluate('location.hash="review"');page.wait_for_selector('[data-review-rep-picker]')
 summary['reviewSelectorRight']=page.locator('.athlete-review-aside [data-review-rep-picker]').count()==1
 summary['reviewFeedbackRight']=page.locator('.athlete-review-aside .athlete-rep-detail').count()==1
 print(json.dumps(summary));browser.close()
