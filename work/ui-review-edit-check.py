import json, httpx
from playwright.sync_api import sync_playwright, expect
base="http://127.0.0.1:8001"
job=next(j for j in httpx.get(base+"/api/videos").json() if j['status']=='completed')
with sync_playwright() as p:
 browser=p.chromium.launch()
 page=browser.new_page(viewport={'width':1440,'height':1000})
 errors=[];saved=[];accepts=[]
 page.on('pageerror',lambda error:errors.append(str(error)))
 page.add_init_script("localStorage.setItem('fencecoach.videoJob',"+json.dumps(job['job_id'])+");")
 def fake_job(route):
  data=route.fetch().json();data['status']='review_ready';route.fulfill(json=data)
 page.route(base+'/api/videos/'+job['job_id'],fake_job)
 def fake_list(route):
  data=route.fetch().json()
  for item in data:
   if item['job_id']==job['job_id']:item['status']='review_ready'
  route.fulfill(json=data)
 page.route(base+'/api/videos',fake_list)
 def annotations(route):
  if route.request.method=='PUT':
   data=route.request.post_data_json;saved.append(data);route.fulfill(json=data)
  else:route.continue_()
 page.route('**/annotations',annotations)
 def accept(route):
  accepts.append(route.request.post_data_json);route.fulfill(status=503,json={'detail':'Isolated check: not saved to real session'})
 page.route('**/accept',accept)
 page.goto(base+'/#analysis',wait_until='networkidle')
 page.wait_for_selector('[data-rep-picker]')
 candidate=page.locator('[data-rep-time-field="onset_ms"]').get_attribute('data-candidate')
 page.locator('[data-rep-time-field="onset_ms"]').fill('0.700')
 page.locator('[data-cycle-review="step_or_reset"]').click()
 expect(page.locator('[data-cycle-review="step_or_reset"]')).to_have_attribute('aria-pressed','true')
 page.locator('[data-rep-time-field="onset_ms"]').fill('0.800')
 page.locator('[data-cycle-review="lunge"]').click()
 expect(page.locator('[data-cycle-review="lunge"]')).to_have_attribute('aria-pressed','true')
 assert saved[-1]['rep_reviews'][0]['start_ms']==800
 page.locator('[data-missed-rep-add]').click()
 for key,time in [('start_ms',9),('peak_ms',10),('end_ms',11)]:
  page.locator('#analysis-video').evaluate('(v,t)=>v.currentTime=t',time)
  page.locator('[data-missed-rep-mark="'+key+'"]').click()
 page.locator('[data-missed-rep-save]').click()
 expect(page.locator('[data-missed-rep-add]')).to_be_visible()
 count=page.locator('[data-rep-picker] option').count()
 page.locator('[data-rep-picker]').select_option(str(count-1))
 expect(page.locator('[data-window-field="end_ms"]')).to_be_visible()
 page.locator('[data-window-field="end_ms"]').fill('11.200')
 page.locator('[data-video-accept]').click()
 expect(page.locator('[data-save-help]')).to_contain_text('Could not save')
 assert accepts and any(w.get('onset_ms')==800 for w in accepts[-1]['windows'])
 assert any(w.get('end_ms')==11200 for w in accepts[-1]['windows'])
 assert any(r.get('candidate_id') is None and r.get('end_ms')==11200 for r in saved[-1]['rep_reviews'])
 print(json.dumps({'checks':['excluded rep timing retained on relabel','timing saved in session payload','missed rep marking','manual rep timing synced to annotation','failed save retains draft'],'movementChoices':count,'errors':errors,'realWrites':0}))
 browser.close()
