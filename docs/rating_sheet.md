# Frozen fewshot-v7 rating sheet

Acceptable means natural, answers the question, uses the readings where relevant, no invented content, no repeating itself. Reasons: robotic, repeated, vague, overreach, wrong, off-topic, good.

Invented? means an invented target, drill, measurement or assumed problem. Blank replies are unrun or failed; see the matching raw transcript for status. Rating columns are left for the owner. Older-prompt replies are excluded.

Current live-first reading scope: Qwen C15,C17,C12,C14 plus C01; Gemini C01 only, after live acceptance. Existing unrun C03/C13/C19 plan rows are retained outside the active scope, not marked as failures.

## Groq — qwen/qwen3.8-27b

| Chain | Turn | Athlete question | Verbatim coach reply | Acceptable (Y/N) | One-word reason | Invented? (Y/N) |
|---|---|---|---|---|---|---|
| C01 | 1 | how's my arm extension? | Your arm extension is inconsistent across the reps. The elbow angle ranges from 145.7 to 174.4 degrees, meaning some lunges finish with a much straighter arm than others. The usual cue is to keep the elbow, forearm, and point in one line, so that variation suggests the arm isn't fully straightening every time. |  |  |  |
| C01 | 2 | is it good? |  |  |  |  |
| C01 | 3 | what should I change? |  |  |  |  |
| C01 | 4 | and my recovery? |  |  |  |  |
| C03 | 1 | how was my torso? |  |  |  |  |
| C03 | 2 | is it good? |  |  |  |  |
| C03 | 3 | what should I change? |  |  |  |  |
| C03 | 4 | and my rear leg? |  |  |  |  |
| C13 | 1 | is it good? |  |  |  |  |
| C13 | 2 | my rear leg |  |  |  |  |
| C13 | 3 | what should I change? |  |  |  |  |
| C13 | 4 | why does that matter? |  |  |  |  |
| C19 | 1 | my arm at the finish |  |  |  |  |
| C19 | 2 | start over |  |  |  |  |
| C19 | 3 | what should I improve? |  |  |  |  |
| C19 | 4 | my front leg |  |  |  |  |

## Gemini — gemini-3.8-flash

| Chain | Turn | Athlete question | Verbatim coach reply | Acceptable (Y/N) | One-word reason | Invented? (Y/N) |
|---|---|---|---|---|---|---|
| C01 | 1 | how's my arm extension? |  |  |  |  |
| C01 | 2 | is it good? |  |  |  |  |
| C01 | 3 | what should I change? |  |  |  |  |
| C01 | 4 | and my recovery? |  |  |  |  |
| C03 | 1 | how was my torso? |  |  |  |  |
| C03 | 2 | is it good? |  |  |  |  |
| C03 | 3 | what should I change? |  |  |  |  |
| C03 | 4 | and my rear leg? |  |  |  |  |
| C13 | 1 | is it good? |  |  |  |  |
| C13 | 2 | my rear leg |  |  |  |  |
| C13 | 3 | what should I change? |  |  |  |  |
| C13 | 4 | why does that matter? |  |  |  |  |
| C19 | 1 | my arm at the finish |  |  |  |  |
| C19 | 2 | start over |  |  |  |  |
| C19 | 3 | what should I improve? |  |  |  |  |
| C19 | 4 | my front leg |  |  |  |  |
## Archived live-app acceptance — fewshot-v7

Provider/model, fallback reason and latency are recorded per turn in [live_acceptance.md](live_acceptance.md). These are live conversations; the evaluation chains remain single-model.

| Chain | Turn | Athlete question | Verbatim coach reply | Acceptable (Y/N) | One-word reason | Invented? (Y/N) |
|---|---|---|---|---|---|---|
| L01 | 1 | how's my arm extension? | Your arm extension is inconsistent across the reps. The elbow angle varies from about 146 to 174 degrees, meaning some lunges finish with a fairly straight arm while others remain noticeably bent. The usual cue is to keep the elbow, forearm, and point in one line, so that variation suggests the arm isn't fully extending every time. |  |  |  |
| L01 | 2 | is it good? | It is inconsistent. Your arm extension varies across the reps, with some finishing much straighter than others, so it does not yet match the cue of keeping the arm in a consistent line. |  |  |  |
| L01 | 3 | what should I change? | Focus on fully straightening the weapon arm before the lunge begins so the extension is already locked in when your feet move. Many coaches teach the "hand first, then feet" sequence, which helps ensure the arm is extended and aimed before the body launches forward. |  |  |  |



## Live-app acceptance — fewshot-v7.1

Fresh chain live-v71-L01; no successful model reply yet. The quota attempt is retained in live_acceptance.md, not rated or counted as a reply.

| Case | Turn | Athlete | Coach | Good | Bad | Comment |
|---|---|---|---|---|---|---|

# v6 comparison (archived)

# Frozen fewshot-v6 rating sheet

Acceptable means natural, answers the question, uses the readings where relevant, no invented content, no repeating itself. Reasons: robotic, repeated, vague, overreach, wrong, off-topic, good.

Invented? means an invented target, drill, measurement or assumed problem. Blank replies are unrun or failed; see the matching raw transcript for status. Rating columns are left for the owner. Older-prompt replies are excluded.

## Groq — qwen/qwen3.8-27b

| Chain | Turn | Athlete question | Verbatim coach reply | Acceptable (Y/N) | One-word reason | Invented? (Y/N) |
|---|---|---|---|---|---|---|
| C19 | 1 | my arm at the finish | Your arm at the finish is inconsistent. The elbow angle varies from 145.7 to 174.4 degrees across reps, meaning some lunges end with a fairly straight arm while others remain noticeably bent. The usual cue is to keep the elbow, forearm, and point in one line, so that variation suggests the arm isn’t fully extending every time. |  |  |  |
| C19 | 2 | start over | No problem, we're starting fresh. This session has 8 recorded reps with usable measurements covering arm extension and direction, front and rear knee angles, torso position, lunge timing and hip speed, and recovery. Which area would you like to look at first? |  |  |  |
| C19 | 3 | what should I improve? | I can see your arm extension, front and rear knee angles, torso position, timing and recovery across eight reps. To point you to the most useful thing to work on, which area are you most curious about: your weapon arm, your front leg, or your recovery? |  |  |  |
| C19 | 4 | my front leg | Your front knee stays behind the toe on every rep, which matches the usual cue for landing with the knee over the ankle rather than past the toes. The bend varies quite a bit, ranging from about 117 to 144 degrees, so your depth is inconsistent from one lunge to the next. |  |  |  |
| C01 | 1 | how's my arm extension? | Your arm extension is inconsistent across these reps. The elbow angle ranges from 145.7 to 174.4 degrees, meaning some lunges finish with a much straighter arm than others. The usual cue is to keep the elbow, forearm, and point in one line, so that variation suggests the arm isn't fully straightening every time. |  |  |  |
| C01 | 2 | is it good? | It’s inconsistent, so I can’t call it good across the board. The elbow angles vary from 145.7 to 174.4 degrees, meaning some reps finish much straighter than others. The cue is to keep that arm in one line, so the variation shows the extension isn’t reliable yet. |  |  |  |
| C01 | 3 | what should I change? | Focus on straightening the weapon arm fully before the lunge finishes, keeping the elbow, forearm, and point in one line. The variation in your elbow angles suggests the arm isn’t consistently reaching full extension, so cue yourself to push the hand out completely rather than letting it lag or bend at the end. |  |  |  |
| C01 | 4 | and my recovery? |  |  |  |  |
| C03 | 1 | how was my torso? |  |  |  |  |
| C03 | 2 | is it good? |  |  |  |  |
| C03 | 3 | what should I change? |  |  |  |  |
| C03 | 4 | and my rear leg? |  |  |  |  |
| C13 | 1 | is it good? |  |  |  |  |
| C13 | 2 | my rear leg |  |  |  |  |
| C13 | 3 | what should I change? |  |  |  |  |
| C13 | 4 | why does that matter? |  |  |  |  |
| C15 | 1 | my front knee in rep 2 |  |  |  |  |
| C15 | 2 | does it go past my toe? |  |  |  |  |
| C15 | 3 | does that mean it caves inward? |  |  |  |  |
| C15 | 4 | what can you say from this view? |  |  |  |  |
| C17 | 1 | how is my recovery? |  |  |  |  |
| C17 | 2 | does that time include holding the lunge? |  |  |  |  |
| C17 | 3 | is it good? |  |  |  |  |
| C17 | 4 | what should I practice? |  |  |  |  |
| C12 | 1 | my torso or my arm? |  |  |  |  |
| C12 | 2 | the second option |  |  |  |  |
| C12 | 3 | at starting guard? |  |  |  |  |
| C12 | 4 | back to the finish |  |  |  |  |
| C14 | 1 | hello |  |  |  |  |
| C14 | 2 | how did I do? |  |  |  |  |
| C14 | 3 | thanks |  |  |  |  |
| C14 | 4 | and my recovery? |  |  |  |  |

## Gemini — gemini-3.8-flash

| Chain | Turn | Athlete question | Verbatim coach reply | Acceptable (Y/N) | One-word reason | Invented? (Y/N) |
|---|---|---|---|---|---|---|
| C01 | 1 | how's my arm extension? | Your arm extension is inconsistent at the finish across your lunges. Many coaches teach extending the weapon arm toward the target without locking the elbow, but your elbow angle spans a wide range from about 146 degrees to 174 degrees. That means on some finishes you reach a nearly straight extension, while on others your arm stays noticeably bent. |  |  |  |
| C01 | 2 | is it good? | It is not consistently good. While you reach the desired straight finish on some lunges, your arm remains partly bent on others, so it does not reliably meet the cue to extend fully toward the target. |  |  |  |
| C01 | 3 | what should I change? | Focus on reaching a complete, straight extension without locking the elbow on every rep, rather than letting the arm stay bent on some lunges. Many coaches teach practicing the slow-motion lunge drill, moving through the extension deliberately so you can feel and hold that straight finish before recovering. |  |  |  |
| C01 | 4 | and my recovery? | There is no set standard or target time for recoveries, but your durations varied across these lunges. Your active return time ranged from about 0.07 seconds to 0.17 seconds, while your total time from finish back to guard spanned roughly 0.27 seconds to 0.57 seconds. Many coaches teach that the key is sequencing the return so the body pulls back while the weapon arm retracts last. |  |  |  |
| C03 | 1 | how was my torso? | That's solid, as your finish position matches the cue to keep your torso upright or only slightly forward. Across your lunges, your tilt remained between 5.4 and 9.8 degrees from vertical. You maintained that position consistently without tipping into heavy forward lean. |  |  |  |
| C03 | 2 | is it good? | Yes, that's good for the torso. Across the session, you avoided heavy forward lean and stayed upright on every lunge. Keep in mind this verdict applies only to your body position, not your blade or footwork. |  |  |  |
| C03 | 3 | what should I change? | Nothing needs changing on your torso, as your posture already fits the coaching cue to stay upright. Since that position is working well, you can keep practicing it as is or move on to check your arm extension or leg lines. If you want to reinforce that stability, many coaches use balance lunges where you hold the finish position and recover using your legs and core. |  |  |  |
| C03 | 4 | and my rear leg? | That's good, as your finish aligns with the cue to finish with a straight rear leg. Across your recorded lunges, your rear knee measured between 175 and 178 degrees, showing a nearly straight line every time. This verdict applies strictly to your knee extension at the finish, not your rear foot contact or push direction. |  |  |  |
| C13 | 1 | is it good? | Across your eight recorded lunges, we have usable readings covering arm extension, leg positions, torso, timing, and recovery. Do you mean your weapon arm, front leg, or recovery? |  |  |  |
| C13 | 2 | my rear leg | That's solid. At your finish, your rear knee stays nearly straight across all your measured lunges, ranging from about 175 to 178 degrees. That matches the usual cue to end with a straightened rear leg driving the body forward. Keep in mind this view cannot evaluate whether your rear foot rolls or stays flat. |  |  |  |
| C13 | 3 | what should I change? | You do not need to change your rear leg extension at the finish, as that straight line is already consistent. If you want to refine the drive itself, many coaches teach focusing on pushing down into the floor with the whole rear foot rather than pushing backward. We could also check another area from this session, like your front leg or arm extension. |  |  |  |
| C13 | 4 | why does that matter? | Applying downward pressure into the floor gives you firm traction to propel your mass directly toward the target. When fencers push backward instead, power is wasted and the rear foot is prone to rolling or lifting. Fully extending that back leg also helps establish a stable, balanced base to complete the hit and recover smoothly. |  |  |  |
| C19 | 1 | my arm at the finish | Your arm extension at the finish is inconsistent across the session. Many coaches teach extending the weapon arm toward the target without locking the elbow, but your elbow angle ranges from 146 degrees to 174 degrees at the finish. Some finishes show a noticeably straight arm while others leave a clear bend. |  |  |  |
| C19 | 2 | start over | We can start fresh. Across your eight recorded lunges, we have usable data on your arm extension, front and rear knees, torso angle, timing, and recovery. Which part of your lunge would you like to look at first? |  |  |  |
| C19 | 3 | what should I improve? | This session covers eight recorded reps with usable readings for your arm extension and direction, front and rear knees, torso, timing, and recovery. Do you mean your weapon arm, front leg, or recovery? |  |  |  |
| C19 | 4 | my front leg | Your front knee stays well behind your front toe at the finish of every recorded rep, ranging between 0.44 and 0.64 torso lengths behind it. That cleanly avoids the common error of letting the knee drift past the toes. Your front knee angle stays relatively open at the finish across the session, landing between 117 and 144 degrees. |  |  |  |

# v5 comparison (archived)

# Frozen fewshot-v5 rating sheet

Acceptable means natural, answers the question, uses the readings where relevant, no invented content, no repeating itself. Reasons: robotic, repeated, vague, overreach, wrong, off-topic, good.

Invented? means an invented target, drill, measurement or assumed problem. Blank replies are unrun or failed; see the matching raw transcript for status. Rating columns are left for the owner. Older-prompt replies are excluded.

## Groq — qwen/qwen3.8-27b

| Chain | Turn | Athlete question | Verbatim coach reply | Acceptable (Y/N) | One-word reason | Invented? (Y/N) |
|---|---|---|---|---|---|---|
| C01 | 1 | how's my arm extension? | Your arm extension at the finish is inconsistent. The elbow angle ranges from 145.7 to 174.4 degrees across the reps, meaning some lunges end with a noticeably bent arm while others are much straighter. Since the knowledge base doesn't define a specific angle cutoff for a "good" extension, I can't call any single rep perfect, but the variation suggests the arm isn't fully straightening reliably on every lunge. The KB emphasizes keeping the elbow, forearm, guard, and point in one line without locking, so the goal is consistent, controlled extension rather than maximum straightness. |  |  |  |
| C01 | 2 | is it good? | No, it’s not good in the sense of being consistent. The arm extension varies significantly across your reps, with the elbow angle ranging from 145.7 to 174.4 degrees. Since a good lunge requires the point to stay aimed and the arm to extend reliably without dropping or chopping, this inconsistency means the arm isn’t meeting the standard of controlled, consistent extension on every rep. |  |  |  |
| C01 | 3 | what should I change? | Focus on keeping the weapon shoulder relaxed and the elbow tucked in line with the forearm and point. The knowledge base suggests that a tight or lifted shoulder often causes the arm to drop or bend inconsistently during the lunge. Try the relaxed-shoulder drill: hold your arm extended and aimed at a target, then jump up and down without letting the point move. This helps train the shoulder to stay loose so the arm can extend fully and consistently on every lunge. |  |  |  |
| C01 | 4 | and my recovery? | Your recovery timing is quite consistent across the session. The active recovery phase, which is the time from when your hips start moving back until you return to guard, ranges from 0.066 to 0.167 seconds. The total time from the finish of the lunge to returning to guard, including any hold, ranges from 0.267 to 0.567 seconds. The knowledge base does not define a specific time target for recovery, so I cannot say if these times are "good" or "bad" against a standard. However, the consistency suggests you are executing the backward movement reliably. The key technical point from the knowledge base is to ensure the weapon arm retracts last, after the body has withdrawn, to avoid leaving yourself open. Since the footage is a fixed side view, it cannot verify the exact timing of the arm retraction relative to the body, so I can only comment on the overall duration and consistency of the hip movement. |  |  |  |
| C03 | 1 | how was my torso? | Your torso stayed fairly upright through the finish, with the forward lean from your guard position ranging from about six to eleven degrees across the reps. That pattern is consistent with the coaching principle of keeping the torso upright or only slightly forward rather than leaning heavily into the lunge. The later reps showed a bit more forward pitch than the earlier ones, so if you want to tighten that up, the slow-motion lunge drill from the knowledge base is a good way to focus on maintaining a stable torso through the full sequence. |  |  |  |
| C03 | 2 | is it good? | The torso readings are consistent with the upright-or-slightly-forward finish cue, but I can’t call the whole lunge “good” from torso data alone. The forward pitch range is about six to eleven degrees, which fits the principle of avoiding heavy forward lean. If you want a broader verdict, we’d need to look at other measured topics like arm extension, knee angles, or recovery timing. |  |  |  |
| C03 | 3 | what should I change? | The torso readings show a gradual increase in forward pitch from the early reps to the later ones, which suggests the torso may be leaning a bit more as the session progresses. The knowledge base links heavy forward lean to balance or strength compensation, and recommends slow-motion lunges with a stable torso as a fix. Since the lean is modest and within the “upright or slightly forward” range, this isn’t a major error, but if you want to keep the torso more consistent across reps, practicing slow-motion lunges with a focus on maintaining an upright torso could help. |  |  |  |
| C03 | 4 | and my rear leg? | Your rear leg finished very straight in every rep where it was measured, with the knee angle ranging from about 175 to 178 degrees. That is consistent with the coaching cue for a near-straight rear leg at the finish. The small variation across reps is minor, and the pattern is solid. |  |  |  |
| C13 | 1 | is it good? | This session has eight reps with usable data on arm extension, front knee, rear knee, torso, lunge timing, and recovery. Do you mean your weapon arm, front leg, or recovery? |  |  |  |
| C13 | 2 | my rear leg | Your rear knee finishes very straight across the reps, ranging from about 175 to 178 degrees. That is consistent with the coaching point that the rear leg should end straight in a line from foot through hip to shoulder. One rep (rep 6) is missing a rear-knee reading, so I can’t confirm it was the same, but the seven available reps all show that straight finish. |  |  |  |
| C13 | 3 | what should I change? | Based on the rear-knee finish angles, there isn’t a clear technical gap to fix there; the straightness is consistent with the standard finish cue. If you’re feeling something off, it might be related to how you’re driving that leg. The knowledge base suggests focusing on pushing down into the floor with the whole rear foot rather than pushing backward, which helps generate forward travel. You could try slow-motion lunges to feel that downward push and ensure the rear arm swings back for balance, but the measurements themselves don’t show a problem with the knee angle. |  |  |  |
| C13 | 4 | why does that matter? | The straight rear leg matters because it completes the forward drive that moves your body toward the target. If the rear knee stays bent at the finish, the push is incomplete, which can limit how far and how quickly you travel. A straight line from foot through hip to shoulder also helps you land in a stable position, making it easier to recover or continue with another attack. |  |  |  |
| C19 | 1 | my arm at the finish | Your arm at the finish shows a wide range in how straight it is, with the elbow angle varying from about 146 to 174 degrees across the reps, meaning some lunges ended with a noticeably bent arm while others were much closer to full extension. The arm direction also varied, with the wrist sitting between roughly 16 and 24 degrees above the shoulder line. The knowledge base doesn't define a specific angle cutoff for a "correct" finish, but it does emphasize that the weapon arm should be extended and aimed at the target without dropping on landing, and that a tight shoulder can cause the arm to drop during the lunge. Since the elbow angles here are all fairly open (none are sharply bent), the variation suggests inconsistency in how fully you're extending the arm at the finish rather than a major breakdown. A relaxed-shoulder drill, where you hold the arm extended and aimed while jumping up and down without moving the point, could help stabilize that extension. |  |  |  |
| C19 | 2 | start over | Fresh start. This session has eight recorded reps with usable measurements covering arm extension and direction, front knee, rear knee, torso, lunge timing and hip speed, and recovery. Which area would you like to look at first? |  |  |  |
| C19 | 3 | what should I improve? | Do you mean your weapon arm, front leg, or recovery? |  |  |  |
| C19 | 4 | my front leg |  |  |  |  |
| C05 | 1 | what about my knees and legs? |  |  |  |  |
| C05 | 2 | what should I work on? |  |  |  |  |
| C05 | 3 | and my torso? |  |  |  |  |
| C05 | 4 | is the speed alright? |  |  |  |  |
| C14 | 1 | hello |  |  |  |  |
| C14 | 2 | how did I do? |  |  |  |  |
| C14 | 3 | thanks |  |  |  |  |
| C14 | 4 | and my recovery? |  |  |  |  |
| C12 | 1 | my torso or my arm? |  |  |  |  |
| C12 | 2 | the second option |  |  |  |  |
| C12 | 3 | at starting guard? |  |  |  |  |
| C12 | 4 | back to the finish |  |  |  |  |
| C18 | 1 | my arm in rep 99 |  |  |  |  |
| C18 | 2 | then the second rep |  |  |  |  |
| C18 | 3 | is it good? |  |  |  |  |
| C18 | 4 | how about the last rep? |  |  |  |  |
| C16 | 1 | how straight was my back? |  |  |  |  |
| C16 | 2 | does the tilt say I leaned forward? |  |  |  |  |
| C16 | 3 | what would you change? |  |  |  |  |
| C16 | 4 | why? |  |  |  |  |
| C17 | 1 | how is my recovery? |  |  |  |  |
| C17 | 2 | does that time include holding the lunge? |  |  |  |  |
| C17 | 3 | is it good? |  |  |  |  |
| C17 | 4 | what should I practice? |  |  |  |  |
| C02 | 1 | how was my rear leg? |  |  |  |  |
| C02 | 2 | is it better straighter or bent? |  |  |  |  |
| C02 | 3 | the second rep |  |  |  |  |
| C02 | 4 | why does that matter? |  |  |  |  |
| C04 | 1 | how did I do? |  |  |  |  |
| C04 | 2 | what should I focus on first? |  |  |  |  |
| C04 | 3 | why does that matter? |  |  |  |  |
| C04 | 4 | thanks |  |  |  |  |
| C06 | 1 | how was my blade control? |  |  |  |  |
| C06 | 2 | did the point drop on landing? |  |  |  |  |
| C06 | 3 | what can you actually tell from my arm? |  |  |  |  |
| C06 | 4 | what should I try? |  |  |  |  |
| C07 | 1 | what was my lunge speed in metres per second? |  |  |  |  |
| C07 | 2 | can you estimate it? |  |  |  |  |
| C07 | 3 | what can you compare instead? |  |  |  |  |
| C07 | 4 | the second rep |  |  |  |  |
| C08 | 1 | how much force did I push with? |  |  |  |  |
| C08 | 2 | does a straighter back leg prove more force? |  |  |  |  |
| C08 | 3 | what does the measurement tell you? |  |  |  |  |
| C08 | 4 | give me one cue |  |  |  |  |
| C09 | 1 | teach me the Dragonfly triple-hop drill |  |  |  |  |
| C09 | 2 | is that in your knowledge base? |  |  |  |  |
| C09 | 3 | give me a drill that is |  |  |  |  |
| C09 | 4 | why that one? |  |  |  |  |
| C10 | 1 | how should I do a fleche? |  |  |  |  |
| C10 | 2 | how should my legs move? |  |  |  |  |
| C10 | 3 | and for a lunge instead? |  |  |  |  |
| C10 | 4 | back to the fleche |  |  |  |  |
| C11 | 1 | my arm in the second rep |  |  |  |  |
| C11 | 2 | and my recovery? |  |  |  |  |
| C11 | 3 | back to my arm |  |  |  |  |
| C11 | 4 | what should I change? |  |  |  |  |
| C15 | 1 | my front knee in rep 2 |  |  |  |  |
| C15 | 2 | does it go past my toe? |  |  |  |  |
| C15 | 3 | does that mean it caves inward? |  |  |  |  |
| C15 | 4 | what can you say from this view? |  |  |  |  |
| C20 | 1 | how was the lunge? |  |  |  |  |
| C20 | 2 | did my rear foot roll? |  |  |  |  |
| C20 | 3 | did I keep the point steady? |  |  |  |  |
| C20 | 4 | what is one thing I can work on from the measurements? |  |  |  |  |

## Gemini — gemini-3.8-flash

| Chain | Turn | Athlete question | Verbatim coach reply | Acceptable (Y/N) | One-word reason | Invented? (Y/N) |
|---|---|---|---|---|---|---|
| C01 | 1 | how's my arm extension? | Your weapon elbow shows an extended finish across your lunges, though it varies from a slight bend around 146 degrees to a straighter finish near 174 degrees. Coaching guidance emphasizes extending the weapon arm toward the target without locking the elbow, and your finish angles reflect that pattern rather than a fully locked joint. Keep in mind that these finish measurements reflect the final position rather than whether the arm initiated the motion before the feet, and fixed side-view pose tracking cannot verify point drop or blade aim. |  |  |  |
| C01 | 2 | is it good? | It cannot be called fully good because the degree of extension fluctuates considerably across your attacks rather than remaining reliably consistent. While coaching principles call for reaching toward the opponent without locking the joint, your finishes range from noticeably bent to almost fully straight, and this side view cannot determine whether your point stayed on target throughout the motion. |  |  |  |
| C01 | 3 | what should I change? | Aim for a consistent, relaxed finish by extending fully toward the target without letting the elbow stay overly bent or snap rigid. You can work on this using the slow-motion lunge drill, where you practice the complete extension at a controlled pace before introducing maximum speed. |  |  |  |
| C01 | 4 | and my recovery? | Your active return to guard ranged from under a tenth of a second up to around two tenths, showing a quick backward pull once your hips began retreating. Many coaches teach that a proper backward recovery requires unlocking the rear knee, driving with both legs, and keeping the weapon arm extended until the body has pulled back. Because our side-view video tracks body positions rather than the precise sequence of arm retraction, it cannot confirm whether your blade remained out until your stance was re-established. Practicing slow-motion recoveries with an explicit focus on retracting the weapon arm last will help reinforce that balance. |  |  |  |
| C03 | 1 | how was my torso? |  |  |  |  |
| C03 | 2 | is it good? |  |  |  |  |
| C03 | 3 | what should I change? |  |  |  |  |
| C03 | 4 | and my rear leg? |  |  |  |  |
| C13 | 1 | is it good? |  |  |  |  |
| C13 | 2 | my rear leg |  |  |  |  |
| C13 | 3 | what should I change? |  |  |  |  |
| C13 | 4 | why does that matter? |  |  |  |  |
| C19 | 1 | my arm at the finish |  |  |  |  |
| C19 | 2 | start over |  |  |  |  |
| C19 | 3 | what should I improve? |  |  |  |  |
| C19 | 4 | my front leg |  |  |  |  |

V4 rows are archived separately in [rating_sheet_v4_archive.md](rating_sheet_v4_archive.md). Gemini C01-T4/C03-T4 there are invalid evaluation inputs, not quality evidence.


V4 rows remain separately archived in [rating_sheet_v4_archive.md](rating_sheet_v4_archive.md).


V4 rows remain separately archived in [rating_sheet_v4_archive.md](rating_sheet_v4_archive.md).

