"""Cabin layouts for the seat map.

The aircraft only stores a total seat count, so the layout (how many seats
per row, which rows are business) is derived from it. Small jets have 3-3
economy rows, the A330 size has 2-4-2 and the biggest one has 3-4-3.
"""
import math

LETTERS = "ABCDEFGHJK"  # no I, like real airlines


def cabin_config(total_seats):
    """Return (business_groups, economy_groups, business_rows) for a seat count."""
    if total_seats >= 340:
        return [1, 2, 1], [3, 4, 3], 6
    if total_seats >= 280:
        return [1, 2, 1], [2, 4, 2], 6
    if total_seats >= 200:
        return [2, 2], [3, 3], 3
    return [2, 2], [3, 3], 2


def _split(letters, groups):
    out, i = [], 0
    for g in groups:
        out.append(letters[i:i + g])
        i += g
    return out


def build_plan(total_seats):
    """Cabins -> rows -> groups of seat numbers, front of the plane first."""
    biz_groups, eco_groups, biz_rows = cabin_config(total_seats)
    biz_width, eco_width = sum(biz_groups), sum(eco_groups)
    biz_total = min(biz_rows * biz_width, total_seats)
    eco_total = total_seats - biz_total

    cabins, row_no = [], 1
    for name, groups, width, count in (
        ("business", biz_groups, biz_width, biz_total),
        ("economy", eco_groups, eco_width, eco_total),
    ):
        rows, left = [], count
        for _ in range(math.ceil(count / width) if count else 0):
            n = min(width, left)
            left -= n
            letters = LETTERS[:n]
            rows.append({
                "row": row_no,
                "groups": [[f"{row_no}{c}" for c in g] for g in _split(letters, groups) if g],
            })
            row_no += 1
        cabins.append({"name": name, "groups": groups, "rows": rows})

    eco_rows = cabins[1]["rows"]
    exit_rows = []
    if len(eco_rows) > 12:
        exit_rows = [eco_rows[8]["row"], eco_rows[9]["row"]]
    return {"cabins": cabins, "exit_rows": exit_rows}


def seat_list(total_seats):
    """Flat list of (seat_number, class) in front-to-back order."""
    out = []
    for cabin in build_plan(total_seats)["cabins"]:
        for row in cabin["rows"]:
            for group in row["groups"]:
                for number in group:
                    out.append((number, cabin["name"]))
    return out
