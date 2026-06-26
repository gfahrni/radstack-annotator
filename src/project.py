"""
Project save/load for RadStack Annotator.
Serializes annotations, LinkedGroups, and viewer state to JSON sidecar files.
"""

import json
import os

from .annotations import Arrow, Rect, Oval, TextBox, LinkedGroup


def _annotation_to_dict(anno):
    base = {
        "slice_idx": anno.slice_idx,
        "color": list(anno.color),
        "width": anno.width,
        "locked": anno.locked,
    }
    if isinstance(anno, Arrow):
        d = {"type": "arrow"}
        d.update(x1=anno.x1, y1=anno.y1, x2=anno.x2, y2=anno.y2)
    elif isinstance(anno, Rect):
        d = {"type": "rect"}
        d.update(x1=anno.x1, y1=anno.y1, x2=anno.x2, y2=anno.y2)
    elif isinstance(anno, Oval):
        d = {"type": "oval"}
        d.update(x1=anno.x1, y1=anno.y1, x2=anno.x2, y2=anno.y2)
    elif isinstance(anno, TextBox):
        d = {"type": "text"}
        d.update(x1=anno.x1, y1=anno.y1, x2=anno.x2, y2=anno.y2,
                 text=anno.text, font_size=anno.font_size,
                 show_background=anno.show_background)
    else:
        raise ValueError(f"Unknown annotation type: {type(anno)}")
    d.update(base)
    return d


def _dict_to_annotation(d):
    cls = {"arrow": Arrow, "rect": Rect, "oval": Oval, "text": TextBox}[d["type"]]
    kwargs = dict(x1=d["x1"], y1=d["y1"], x2=d["x2"], y2=d["y2"],
                  slice_idx=d["slice_idx"], color=tuple(d["color"]),
                  width=d["width"])
    if d["type"] == "text":
        anno = cls(d["x1"], d["y1"], d["x2"], d["y2"], d["slice_idx"],
                   d["text"], tuple(d["color"]), d["width"],
                   d["font_size"], d["show_background"])
    else:
        anno = cls(**kwargs)
    anno.locked = d.get("locked", False)
    return anno


def save(filepath, annotations, linked_groups, slice_idx,
         current_color, current_width):
    """
    Serialize all project state to a JSON file.

    Parameters
    ----------
    filepath : str
        Path for the .radproj file.
    annotations : dict[int, list]
        slice_idx -> list of annotation objects.
    linked_groups : list[LinkedGroup]
    slice_idx : int
        Current active slice.
    current_color : tuple[int,int,int]
    current_width : int
    """
    anno_list = []
    refs = {}  # id(anno) -> list index in anno_list

    for sidx in sorted(annotations):
        for anno in annotations[sidx]:
            refs[id(anno)] = len(anno_list)
            anno_list.append(_annotation_to_dict(anno))

    group_list = []
    for g in linked_groups:
        si = refs.get(id(g.start_anno), -1)
        ei = refs.get(id(g.end_anno), -1)
        group_list.append({
            "start_slice": g.start_slice,
            "end_slice": g.end_slice,
            "start_anno_idx": si,
            "end_anno_idx": ei,
        })

    data = {
        "version": 1,
        "slice_idx": slice_idx,
        "current_color": list(current_color),
        "current_width": current_width,
        "annotations": anno_list,
        "linked_groups": group_list,
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load(filepath):
    """
    Deserialize project state from a JSON file.

    Returns a dict with keys:
        annotations    : dict[int, list]  (slice_idx -> list of annotation objects)
        linked_groups  : list[LinkedGroup]
        slice_idx      : int
        current_color  : tuple[int,int,int]
        current_width  : int

    Returns None if the file cannot be read or is invalid.
    """
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, IOError):
        return None

    if not isinstance(data, dict) or data.get("version") != 1:
        return None

    flat_annos = []
    for d in data.get("annotations", []):
        try:
            anno = _dict_to_annotation(d)
            flat_annos.append(anno)
        except (KeyError, ValueError, TypeError):
            continue

    annotations = {}
    for anno in flat_annos:
        annotations.setdefault(anno.slice_idx, []).append(anno)

    linked_groups = []
    for gd in data.get("linked_groups", []):
        si = gd.get("start_anno_idx", -1)
        ei = gd.get("end_anno_idx", -1)
        if 0 <= si < len(flat_annos) and 0 <= ei < len(flat_annos):
            g = LinkedGroup(gd["start_slice"], gd["end_slice"],
                            flat_annos[si], flat_annos[ei])
            linked_groups.append(g)

    return {
        "annotations": annotations,
        "linked_groups": linked_groups,
        "slice_idx": data.get("slice_idx", 0),
        "current_color": tuple(data.get("current_color", [255, 255, 255])),
        "current_width": data.get("current_width", 3),
    }


def default_path(data_path):
    """Return the default .radproj path beside the image folder."""
    parent = os.path.dirname(os.path.abspath(data_path))
    folder_name = os.path.basename(os.path.normpath(data_path))
    return os.path.join(parent, folder_name + ".radproj")
