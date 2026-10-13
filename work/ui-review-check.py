import json, httpx, time
from pathlib import Path
from playwright.sync_api import sync_playwright
base = "http://127.0.0.1:8001"
jobs = httpx.get(base + "/api/videos").json()
job = next(j for j in jobs if j["status"] in ["completed", "review_ready"])
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width":1440,"height":1000})
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)))
    page.add_init_script("localStorage.setItem('fencecoach.videoJob', " + json.dumps(job["job_id"]) + ");")
    page.goto(base + "/#analysis",wait_until="networkidle")
    page.wait_for_selector("[data-rep-picker]")
    summary = page.evaluate("""() => ({cards:document.querySelectorAll('.rep-verification').length,movements:document.querySelector('[data-rep-picker]').options.length,fields:document.querySelectorAll('[data-rep-time-field]').length,scroll:getComputedStyle(document.documentElement).scrollBehavior,bodyTransition:getComputedStyle(document.body).transitionDuration,technical:document.querySelectorAll('.motion-panel,.motion-metrics,.activity-detection,[data-video-export]').length,nodes:document.querySelectorAll('#screen *').length})""")
    page.locator('[data-rep-picker]').select_option('1')
    summary['selected'] = page.locator('[data-rep-picker]').input_value()
    summary['videoTime'] = page.locator('#analysis-video').evaluate('(video)=>video.currentTime')
    summary['cardsAfterSelect'] = page.locator('.rep-verification').count()
    page.screenshot(path='work/analysis-compact-desktop.png',full_page=True)
    durations=[]
    for screen in ['train','progress','analysis','train','analysis']:
        start=time.perf_counter()
        page.evaluate('(screen)=>location.hash=screen',screen)
        page.wait_for_function('(screen)=>document.querySelector("#screen").classList.contains("screen-"+screen)',arg=screen)
        durations.append(round((time.perf_counter()-start)*1000,1))
    summary['navigationMs']=durations
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path='work/analysis-compact-mobile.png',full_page=True)
    summary['mobileOverflow']=page.evaluate('document.documentElement.scrollWidth > innerWidth')
    summary['errors']=errors
    print(json.dumps(summary))
    browser.close()
