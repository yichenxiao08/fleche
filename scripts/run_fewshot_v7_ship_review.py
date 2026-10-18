"""Owner-authorized expanded reading scope; frozen v7 writer sources stay intact."""

import re

import run_fewshot_v7_review as review

ORDERS = {"groq": [15, 17, 12, 14, 1], "gemini": [1]}


def append_new_replies():
    """Fill pending cells and append newly saved turns, preserving existing ratings."""
    path = review.ROOT / "docs/rating_sheet.md"
    content = path.read_text(encoding="utf-8")
    current, archived = content.split("\n# v6 comparison", 1)
    lines = current.splitlines()

    def cell(text):
        return text.replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")

    for provider, heading in (("groq", "## Groq"), ("gemini", "## Gemini")):
        begin = next(i for i, line in enumerate(lines) if line.startswith(heading))
        end = next(
            (i for i in range(begin + 1, len(lines)) if lines[i].startswith("## ")),
            len(lines),
        )
        existing = {}
        for index in range(begin + 1, end):
            if re.match(r"\| C\d{2} \|", lines[index]):
                fields = re.split(r"(?<!\\)\|", lines[index])[1:-1]
                existing[(fields[0].strip(), int(fields[1]))] = (index, fields)
        additions = []
        rows = {row["id"]: row for row in review.rows(provider)}
        for chain in ORDERS[provider]:
            ident = f"C{chain:02d}"
            for turn in rows.get(ident, {}).get("turns", []):
                key = (ident, turn["turn"])
                if key in existing:
                    index, fields = existing[key]
                    if not fields[3].strip():
                        fields[3] = " " + cell(turn["answer"]) + " "
                        lines[index] = "|" + "|".join(fields) + "|"
                else:
                    additions.append(
                        "| "
                        + " | ".join(
                            [
                                ident,
                                str(turn["turn"]),
                                cell(turn["question"]),
                                cell(turn["answer"]),
                                "",
                                "",
                                "",
                            ]
                        )
                        + " |"
                    )
        insert = end
        while insert > begin and not lines[insert - 1].strip():
            insert -= 1
        lines[insert:insert] = additions
    path.write_text("\n".join(lines) + "\n# v6 comparison" + archived, encoding="utf-8")


def main():
    review.ORDERS = ORDERS
    review.rating_sheet = append_new_replies
    scope = review.OUT / "shipping_scope_live_first.json"
    if not scope.exists():
        review.write(
            scope,
            {
                "orders": review.ORDERS,
                "writer": "fewshot-v7",
                "prompt_changes": False,
                "after_live_acceptance": True,
            },
        )
    review.main()


if __name__ == "__main__":
    main()
