// Display formatting only. Saved transcripts and source measurements retain precision.
export function formatCoachText(text = "") {
  let output = String(text)
    .replace(
      /(-?\d+(?:\.\d+)?)\s*[–—-]\s*(-?\d+(?:\.\d+)?)\s*(milliseconds?|msecs?|ms|seconds?|secs?|s)\b/gi,
      (_, a, b, unit) =>
        `${(Number(a) / (/^(ms|millisecond)/i.test(unit) ? 1000 : 1)).toFixed(1)}–${(Number(b) / (/^(ms|millisecond)/i.test(unit) ? 1000 : 1)).toFixed(1)} seconds`,
    )
    .replace(
      /(?<![\w.])(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)(?!\d)/g,
      (_, hours, minutes, seconds) =>
        `${(Number(hours || 0) * 3600 + Number(minutes) * 60 + Number(seconds)).toFixed(1)} seconds`,
    )
    .replace(
      /(-?\d+(?:\.\d+)?)\s*(milliseconds?|msecs?|ms|seconds?|secs?|s)\b/gi,
      (_, number, unit) =>
        `${(Number(number) / (/^(ms|millisecond)/i.test(unit) ? 1000 : 1)).toFixed(1)} seconds`,
    );
  return output
    .split(/\n\s*\n/)
    .map((paragraph) =>
      paragraph
        .split(/(?<=[.!?])\s+/)
        .filter(
          (sentence) =>
            !/^(?:note that\b|keep in mind\b|as an ai\b|(?:this|these|the) (?:2d|2-d|image-plane) (?:measurement|measurements|estimate|estimates)\b|this is a (?:basic.drill review flag|provisional)|no flags (?:does not|doesn't))/i.test(
              sentence.trim(),
            ),
        )
        .join(" "),
    )
    .filter(Boolean)
    .join("\n\n");
}
