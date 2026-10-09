"""Export ten real evaluation answers for an optional usefulness spot check."""

import html
import json
from pathlib import Path


def main():
    project = Path(__file__).resolve().parents[1]
    rows = json.loads((project / "data/evals/coach-answers.json").read_text())
    rows = [r for r in rows if "answer" in r][:10]
    cards = "".join(
        f'<article data-id="{html.escape(r["case_id"])}"><small>{html.escape(r["model"])}</small>'
        f"<h2>{html.escape(r['question'])}</h2><p>{html.escape(r['answer'])}</p>"
        f'<label>Useful? <select><option value="">Not rated</option><option>Yes</option><option>No</option></select></label></article>'
        for r in rows
    )
    page = (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Coach answer review</title>
    <style>body{font:17px system-ui;background:#111;color:#eee;max-width:800px;margin:30px auto;padding:20px}article{padding:24px;border:1px solid #555;border-radius:12px;margin:20px 0}p{white-space:pre-wrap;line-height:1.6}button,select{padding:12px}small{color:#e98b8b}</style>
    <h1>Ten coach answers</h1><p>These are offline diagnostic cases from footage that fails the app's quality gate. A useful answer explains the evidence honestly. This is an optional human usefulness check, not a technique correctness certification.</p>"""
        + cards
        + """<button id="save">Download ratings</button><script>
    document.querySelector('#save').onclick=()=>{const rows=[...document.querySelectorAll('article')].map(a=>({case_id:a.dataset.id,useful:a.querySelector('select').value,reviewer:'human',reviewed_at:new Date().toISOString()}));const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(rows,null,2)],{type:'application/json'}));a.download='coach-usefulness-ratings.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
    </script></html>"""
    )
    destination = project / "data/evals/coach-review.html"
    destination.write_text(page, encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
