import json
import time
from pathlib import Path
from fencecoach.api import coaching_request, repository
from fencecoach.coach.conversation import run_conversation
from fencecoach.coach.providers import chat_model, provider_failure
from fencecoach.schemas import ConversationMessage, ReportRequest

session=repository.list_sessions()[0]
questions=[
    'What would you change first across this set, and why?',
    'How do my sword arm and rear leg compare with my approved examples at the finish?',
    'What about those two things while I am returning to guard?',
]
history=[]
results=[]
for question in questions:
    request=coaching_request(session, ReportRequest(question=question,mode='gemini'))
    request.conversation_history=history.copy()
    started=time.perf_counter()
    try:
        run=run_conversation(request,'gemini',model=chat_model('gemini'))
        row={'question':question,'answer':run.report.summary,'seconds':round(time.perf_counter()-started,2),
             'rep_count':len(request.technique_evaluation.get('reps',[])),
             'trace':[{'step':event.step,'detail':event.detail} for event in run.trace]}
        history.extend([ConversationMessage(role='user',content=question),ConversationMessage(role='assistant',content=run.report.summary)])
        print(json.dumps({k:row[k] for k in ('question','answer','seconds','rep_count')}),flush=True)
        results.append(row)
    except Exception as exc:
        failure=provider_failure(exc)
        row={'question':question,'error_type':type(exc).__name__,'validation_issues':getattr(exc,'validation_issues',[]),'error':failure[1] if failure else 'Live response validation failed.'}
        results.append(row)
        print(json.dumps(row),flush=True)
        break
path=Path('evals/results/coach-general-workflow-2026-10-12.json')
path.write_text(json.dumps({'session_id':session.session_id,'results':results},indent=2),encoding='utf-8')
