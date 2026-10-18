> **Invalid evaluation inputs:** Gemini C01-T4 and C03-T4 were generated with three unanswered earlier user questions in history after 503 outages. Exclude both rows from quality evidence. Raw questions/replies and ratings are preserved; this is an input-validity annotation, not a rating.

# Frozen fewshot-v4 rating sheet

Acceptable means natural, answers the question, uses the readings where relevant, no invented content, no repeating itself. Reasons: robotic, repeated, vague, overreach, wrong, off-topic, good.

Invented? means an invented target, drill, measurement or assumed problem. Blank replies are unrun or failed; see the matching raw transcript for status. Rating columns are left for the owner. Older-prompt replies are excluded.

## Groq — qwen/qwen3.8-27b

| Chain | Turn | Athlete question | Verbatim coach reply | Acceptable (Y/N) | One-word reason | Invented? (Y/N) |
|---|---|---|---|---|---|---|
| C01 | 1 | how's my arm extension? | Your arm extension is inconsistent across the set. The weapon elbow ranges from about 146 to 174 degrees at the finish, meaning some reps end near-straight while others remain noticeably bent. The cue is to straighten the arm toward the target without locking it, so this variation suggests the extension isn't reliable yet. |  |  |  |
| C01 | 2 | is it good? | Not consistently. The cue is to straighten the weapon arm toward the target, and some of your reps finish near-straight while others stay noticeably bent. |  |  |  |
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
| C01 | 1 | how's my arm extension? |  |  |  |  |
| C01 | 2 | is it good? |  |  |  |  |
| C01 | 3 | what should I change? |  |  |  |  |
| C01 | 4 | and my recovery? | I do not have your arm extension readings loaded in this turn to judge your arm or tell you what to change on it, though as general guidance many coaches teach extending the arm fully toward the target without locking the elbow before the feet launch. For your recovery, total time from finish to guard ranged from about 0.3 to 0.6 seconds across your reps. The coaching reference does not set a numerical time standard for recovery, and because these readings do not track whether your arm retracted after your body moved, duration alone cannot show if the recovery was good. |  |  |  |
| C03 | 1 | how was my torso? |  |  |  |  |
| C03 | 2 | is it good? |  |  |  |  |
| C03 | 3 | what should I change? |  |  |  |  |
| C03 | 4 | and my rear leg? | There are no usable torso measurements in this turn's data, so I cannot judge your posture or tell you whether it needs changing. As general guidance, many coaches teach keeping the torso upright or only slightly tilted forward rather than leaning heavily. <br><br>For your rear leg at the finish, every measured rep is consistent with the straight-leg cue, ranging from about 175 to 178 degrees. That part of your finish is solid, though this side view cannot show how your rear foot pressed into the floor or whether it rolled. |  |  |  |
| C13 | 1 | is it good? |  |  |  |  |
| C13 | 2 | my rear leg |  |  |  |  |
| C13 | 3 | what should I change? |  |  |  |  |
| C13 | 4 | why does that matter? |  |  |  |  |
| C19 | 1 | my arm at the finish |  |  |  |  |
| C19 | 2 | start over |  |  |  |  |
| C19 | 3 | what should I improve? |  |  |  |  |
| C19 | 4 | my front leg |  |  |  |  |

