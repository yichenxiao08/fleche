"""Render source-aligned diagnostic overlays, never synthetic training evidence."""

from pathlib import Path


def generate_contact_sheet(result, directory):
    import av
    from PIL import Image, ImageDraw

    from fencecoach.video_preview import upright_frame

    directory = Path(directory)
    frames = result["frames"]
    if not frames:
        raise ValueError("No timestamped samples for a contact sheet.")
    targets = [frames[round(i * (len(frames) - 1) / 11)] for i in range(12)]
    canvas = Image.new("RGB", (1200, 3 * 210), "#151515")
    index, origin = 0, None
    with av.open(str(directory / "source.video")) as container:
        for frame in container.decode(video=0):
            t = float(frame.pts * frame.time_base) * 1000
            origin = t if origin is None else origin
            if index == 12:
                break
            if t - origin < targets[index]["time_ms"]:
                continue
            image = upright_frame(frame).to_image()
            image.thumbnail((300, 175))
            pen = ImageDraw.Draw(image)
            points = targets[index].get("landmarks", [])
            if len(points) == 33:
                for a, b in (
                    (11, 12),
                    (11, 23),
                    (12, 24),
                    (23, 24),
                    (23, 25),
                    (25, 27),
                    (24, 26),
                    (26, 28),
                    (11, 13),
                    (13, 15),
                    (12, 14),
                    (14, 16),
                ):
                    if min(points[a][3:5] + points[b][3:5]) >= 0.5:
                        pen.line(
                            (
                                points[a][0] * image.width,
                                points[a][1] * image.height,
                                points[b][0] * image.width,
                                points[b][1] * image.height,
                            ),
                            fill="#ff3b42",
                            width=2,
                        )
            x, y = index % 4 * 300, index // 4 * 210
            canvas.paste(image, (x, y))
            reps = [
                c.get("rep_number", i + 1)
                for i, c in enumerate(result.get("candidates", []))
                if c.get("onset_ms", c["start_ms"]) <= targets[index]["time_ms"] <= c["end_ms"]
            ]
            ImageDraw.Draw(canvas).text(
                (x + 4, y + 180),
                f"{targets[index]['time_ms'] / 1000:.2f}s | {'rep ' + str(reps[0]) if reps else 'outside proposed rep'}",
                fill="white",
            )
            index += 1
    destination = directory / "contact-sheet.jpg"
    temporary = directory / "contact-sheet.tmp.jpg"
    canvas.save(temporary, quality=90)
    temporary.replace(destination)
    return destination
