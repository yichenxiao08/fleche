# Next-phase live-app acceptance transcripts

Ten scripted conversations through the running FastAPI app's real coaching queue and report endpoints, on fresh clones of real saved sessions. Actual providers answered every turn. Separate SQLite/video-result copies isolated the acceptance app; the user's main app and default remained old.

The L10 fault injection raises one synthetic 429 before a real local invocation; it makes no Gemini call for that failure. State and packet pass through the normal router/repository path. This proves state transfer, not acceptable fallback coaching quality.

```json
{
  "conversations": 10,
  "turns": 37,
  "providers": {
    "gemini": 35,
    "local": 2
  },
  "forced_chain": [
    {
      "turn": 1,
      "provider": "gemini",
      "reason": null,
      "topic": [
        "arm"
      ],
      "reps": []
    },
    {
      "turn": 2,
      "provider": "gemini",
      "reason": null,
      "topic": [
        "arm"
      ],
      "reps": []
    },
    {
      "turn": 3,
      "provider": "local",
      "reason": "rate_limit",
      "topic": [
        "arm"
      ],
      "reps": [
        2
      ]
    },
    {
      "turn": 4,
      "provider": "local",
      "reason": "cooldown:rate_limit",
      "topic": [
        "recovery"
      ],
      "reps": [
        2
      ]
    },
    {
      "turn": 5,
      "provider": "gemini",
      "reason": null,
      "topic": [
        "recovery"
      ],
      "reps": [
        2
      ]
    }
  ],
  "gemini": {
    "http_median_s": 2.14,
    "http_p95_s": 5.42,
    "first_visible_median_s": 2.01,
    "provider_ttft_median_s": null
  },
  "local": {
    "http_median_s": 5.07,
    "http_p95_s": 5.44,
    "first_visible_median_s": 4.17,
    "provider_ttft_median_s": 1.89
  }
}
```

HTTP latency includes request construction, queue/worker overhead and generation. First-visible timing is polled at 250 ms. It is not provider TTFT; Gemini's synchronous provider path supplies no TTFT. Local transport TTFT and first verified visible sentence are separate.

An earlier launcher-isolation failure is preserved in evals/next_phase/live_pre_isolation_failure/. Package import constructed the original repository before process-local settings were applied; the existing worker claimed that test job. No accepted new-core answer was produced. Only the ten launcher-created session rows and that one failed job were removed from the original database after verifying IDs/title/no associated runs. The corrected launcher sets environment before package import and asserts its repository path. Legacy worker request consumption for that invalid attempt was not instrumented; it is not reported as zero.

## L01 — saved-session source H10

Source session: 7bbb26f13ea5467384bc7a1772c399ae; isolated session: e045d9de078845cd828fd274283b81c6. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L01.json.

### T1 — gemini; 2.36s HTTP; reason: primary available

User: how is my arm extension

Across your available reps at the lunge finish, your weapon elbow angle ranges from 145.7 deg on rep 3 to 174.4 deg on rep 5, while your weapon arm direction measures between 15.6 deg on rep 8 and 24.0 deg on rep 4.

### T2 — gemini; 2.23s HTTP; reason: primary available

User: is this good or bad, do i need to make any changes

The measurements show your arm positions across the lunge finishes, but a specific evaluation of good or bad requires a coach-reviewed target or a drill-specific standard that the current footage does not establish.

### T3 — gemini; 1.97s HTTP; reason: primary available

User: the second rep

On your second rep at the lunge finish, your weapon elbow angle measures 168.1 deg and your weapon arm direction is 18.2 deg.

### T4 — gemini; 1.94s HTTP; reason: primary available

User: why does that matter?

That elbow measurement describes how straight your arm is at 168.1 deg, while the direction angle tracks your shoulder-to-wrist alignment relative to the horizontal, though neither metric alone establishes whether your extension is correct without a target standard.

## L02 — saved-session source H08

Source session: 7bbb26f13ea5467384bc7a1772c399ae; isolated session: 5c5f88cb35284c79834bfc8b48fe61a7. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L02.json.

### T1 — gemini; 2.22s HTTP; reason: primary available

User: how was my back leg

Across your lunges, your back leg finished with an angle of 177.6 deg on rep 1, 176.1 deg on rep 2, 177.1 deg on rep 3, 175.5 deg on rep 4, 176.8 deg on rep 5, 174.9 deg on rep 7, and 177.2 deg on rep 8. Those numbers show how straight the knee joint appears in the video, but we need a coach's target or specific standard to judge whether that extension is ideal for your fencing.

### T2 — gemini; 1.95s HTTP; reason: primary available

User: was it good

To evaluate if that extension works well for your fencing, we can look at your overall movement sequence and whether you are getting efficient propulsion from the back foot toward your target.

### T3 — gemini; 2.12s HTTP; reason: primary available

User: and the last rep?

On the last rep, your rear knee angle finished at 177.2 deg. That angle purely describes the position seen in the video and does not indicate whether it was good or bad without a target standard.

## L03 — saved-session source H09

Source session: 7bbb26f13ea5467384bc7a1772c399ae; isolated session: 30eb79d98089422eb8d50e2d8fdcd928. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L03.json.

### T1 — gemini; 1.96s HTTP; reason: primary available

User: how was my torso

At the finish of your lunges, your torso pitch change ranged from 6.0 deg on rep 1 to 10.9 deg on rep 8, with your projected torso tilt measuring between 5.4 deg and 9.8 deg. While we can observe these forward shifts from your guard anchor, we need a coach-reviewed target to grade whether this position is ideal.

### T2 — gemini; 2.22s HTTP; reason: primary available

User: and my rear leg?

At the finish of your lunges, your rear knee angle measured 177.6 deg on rep 1, 176.1 deg on rep 2, 177.1 deg on rep 3, 175.5 deg on rep 4, 176.8 deg on rep 5, 174.9 deg on rep 7, and 177.2 deg on rep 8. While these measurements show how straight your leg is positioned at the end of each lunge, we still need a coach-reviewed target to grade whether this extension is ideal.

### T3 — gemini; 2.00s HTTP; reason: primary available

User: back to my torso

Since we have your forward pitch change and projected tilt numbers across the reps, let's look at how consistent those shifts are, or compare rep 1 at 6.0 deg with rep 8 at 10.9 deg to see how your forward lean increases as you complete the lunge.

### T4 — gemini; 2.05s HTTP; reason: primary available

User: is it good?

That cannot be established because we do not have a grading standard or coach-reviewed target for your torso position.

## L04 — saved-session source H01

Source session: 69f4edba02304f12985963c34b774867; isolated session: 378a249faf214f53a4e19a24d7e57f96. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L04.json.

### T1 — gemini; 2.46s HTTP; reason: primary available

User: how did I do?

I cannot evaluate your overall lunge performance from this footage because the tracking data isn't available. A classical teaching model for a straight lunge uses approximately a right-angle front knee, a straightened rear leg, a planted rear sole, and an erect torso, but these serve as drill references rather than universal correctness thresholds.

### T2 — gemini; 2.00s HTTP; reason: primary available

User: what about my knees and legs

Tracking data is not supported for your legs and knees in this footage, so I cannot measure your front-knee bend or rear-leg extension directly.

### T3 — gemini; 2.02s HTTP; reason: primary available

User: and my speed?

I don't have another supported detail about speed in this packet. A coach-reviewed example of the same phase would help us take this further.

## L05 — saved-session source E12

Source session: 7bbb26f13ea5467384bc7a1772c399ae; isolated session: 273c03b7dc8d4db7a90da4182073fd05. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L05.json.

### T1 — gemini; 1.99s HTTP; reason: primary available

User: How was my blade control?

We do not have weapon tracking for your blade control in this session, so I cannot measure or grade your weapon position from the current footage alone.

### T2 — gemini; 2.14s HTTP; reason: primary available

User: What was my speed in metres per second?

I cannot give your speed in metres per second because your hip speed is measured in 2.01 torso/s on rep 1, 1.95 torso/s on rep 2, 1.43 torso/s on rep 3, 2.18 torso/s on rep 4, 2.67 torso/s on rep 5, 2.27 torso/s on rep 6, 2.39 torso/s on rep 7, and 2.16 torso/s on rep 8, which reflects image-plane horizontal hip speed normalized by initial torso length rather than linear speed in metres per second.

### T3 — gemini; 1.86s HTTP; reason: primary available

User: How much force did I push with?

I cannot measure your push force directly from the video because force tracking requires direct floor sensors rather than video pose estimation alone.

### T4 — gemini; 1.85s HTTP; reason: primary available

User: Give me the Dragonfly triple-hop drill from your library.

I cannot provide the Dragonfly triple-hop drill because that item is not found in the library.

## L06 — saved-session source H07

Source session: 7bbb26f13ea5467384bc7a1772c399ae; isolated session: e500e7995c6b4959beb1682276d705d5. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L06.json.

### T1 — gemini; 1.98s HTTP; reason: primary available

User: my arm in rep 2

At the finish of your lunge in rep 2, your weapon arm direction is measured at 18.2 deg and your weapon elbow angle is 168.1 deg. While these numbers describe your arm position, judging whether this execution is correct requires a coach-reviewed target or standard.

### T2 — gemini; 2.54s HTTP; reason: primary available

User: and my recovery?

In the active recovery phase for rep 2, your estimated active recovery time is measured at 0.100 seconds and your finish to guard time is 0.500 seconds. Because measured recovery times alone do not establish technique quality, comparing these intervals to a coach-reviewed standard or target for your recovery mechanics is needed to assess correctness.

### T3 — gemini; 2.68s HTTP; reason: primary available

User: back to my arm

Since we already looked at your arm's position at the lunge finish in rep 2, let's look at how you set up that extension earlier in the movement or check another rep to compare your arm alignment.

### T4 — gemini; 3.53s HTTP; reason: primary available

User: why does that matter?

As general guidance, for a conventional straight lunge toward a fixed torso-height target, review front-leg bend, rear-leg extension, rear-foot contact, torso control and weapon-arm direction together.

## L07 — saved-session source H02

Source session: 69f4edba02304f12985963c34b774867; isolated session: 01045b27ca2145719d819077cedb1092. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L07.json.

### T1 — gemini; 3.75s HTTP; reason: primary available

User: was it good?

I don't have another supported detail about that question in this packet. A coach-reviewed example of the same phase would help us take this further.

### T2 — gemini; 4.03s HTTP; reason: primary available

User: the first one

Tracking is currently unsupported for rep 1, so I cannot assess your arm position in that finish. To evaluate it, we would need clear tracking of the arm during the lunge finish alongside a coach-reviewed standard.

### T3 — gemini; 2.22s HTTP; reason: primary available

User: what should I focus on?

As general guidance, in the conventional simple-lunge teaching sequence, this arm reaches forward toward the target with the point aimed at it.

## L08 — saved-session source E11

Source session: 7bbb26f13ea5467384bc7a1772c399ae; isolated session: 7315582bf56541c59c072e0e3f7e08d1. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L08.json.

### T1 — gemini; 2.04s HTTP; reason: primary available

User: hello

Hello! Ready to look at your fencing footage whenever you are.

### T2 — gemini; 3.06s HTTP; reason: primary available

User: what can you tell me about this session?

Across your eight lunges, your action-to-lunge times ranged from 0.267 seconds to 0.667 seconds, with front knee angles at the finish spanning from 116.6 deg to 144.3 deg and weapon elbow angles between 145.7 deg and 174.4 deg.

### T3 — gemini; 1.87s HTTP; reason: primary available

User: thanks

You're very welcome. Let me know if you'd like to dive into a specific lunge or look at a particular part of your form.

### T4 — gemini; 2.41s HTTP; reason: primary available

User: start over

Welcome back! We have eight reps saved from your session, so let's pick up where you'd like to continue.

## L09 — saved-session source H04

Source session: 69f4edba02304f12985963c34b774867; isolated session: bfd896e73edc422f83280b689ef73ffe. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L09.json.

### T1 — gemini; 1.94s HTTP; reason: primary available

User: how should a fleche be performed?

The current footage does not track your movements to measure your fleche technique.

### T2 — gemini; 1.96s HTTP; reason: primary available

User: how should my legs move?

The current tracking doesn't capture your leg positions during the fleche.

### T3 — gemini; 2.18s HTTP; reason: primary available

User: should I keep running or stop immediately?

As general guidance, use event sequence, intended touch and movement-specific comparisons rather than a lunge endpoint template to assess a fleche.

## L10 — saved-session source S11

Source session: 7bbb26f13ea5467384bc7a1772c399ae; isolated session: 29c415ef621e4a0e8ced8d1f7c485313. Raw requests, reports, trace, provider reasons and stream snapshots: evals/next_phase/live/L10.json.

### T1 — gemini; 5.16s HTTP; reason: primary available

User: how is my arm extension

Your weapon elbow angle measures 160.0 deg on rep 1, 168.1 deg on rep 2, 145.7 deg on rep 3, 165.4 deg on rep 4, 174.4 deg on rep 5, 159.0 deg on rep 7, and 148.4 deg on rep 8 at the lunge finish, while your weapon arm direction measures between 15.6 deg and 24.0 deg across those reps. These measurements show your arm position at the finish, but determining whether this extension is correct requires a drill-specific standard or coach review.

### T2 — gemini; 5.42s HTTP; reason: primary available

User: why does that matter?

The weapon arm direction measures the angle of your shoulder-to-wrist line against the image horizontal, while the weapon elbow angle shows the bend at your elbow at the lunge finish. These metrics record how your arm is positioned when you complete the lunge, but they do not indicate target alignment or whether the extension timing and technique quality meet your coach's standards.

### T3 — local; 5.44s HTTP; reason: rate_limit

User: the second rep

To assess the quality of your extension, we would need a drill-specific standard or coach-reviewed target.

### T4 — local; 4.70s HTTP; reason: cooldown:rate_limit

User: and my recovery?

Your estimated active recovery time on rep 2 is 0.100 seconds, and your finish to guard time is 0.500 seconds.

### T5 — gemini; 5.42s HTTP; reason: primary available

User: what should I focus on?

According to the training material, recovering back begins by releasing the rear knee and pushing from the front leg to return toward the starting guard position.
