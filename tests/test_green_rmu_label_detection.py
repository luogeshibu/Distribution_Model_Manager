from pathlib import Path

from dmm.domain.gfile.parser import GParser


def _nearest_green_names(path: Path):
    parser = GParser(
        label_regex=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
        max_distance=120.0,
        overlap_tolerance=20.0,
    )
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)

    result = []
    for frame in frames:
        candidates = parser.find_label_candidates(
            parsed,
            frame,
            ["top"],
        )
        green = [c for c in candidates if c.is_green]
        if green:
            chosen = min(green, key=lambda c: (c.score, c.obj.xml_index))
            result.append(chosen.text)
        else:
            result.append("")

    return result
