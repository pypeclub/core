"""Used for scripting

These are used in other scripts and mostly require explicit input,
such as which specific nodes they apply to.

For interactive use, see :mod:`interactive.py`

"""

from maya import cmds

from .. import io, api


def reset_frame_range():
    """Set frame range to current asset"""
    shot = api.Session["AVALON_ASSET"]
    shot = io.find_one({"name": shot, "type": "asset"})

    try:
        edit_in = shot["data"].get("edit_in")
        if edit_in is None:
            edit_in = shot["data"]["fstart"]

        edit_out = shot["data"].get("edit_out")
        if edit_out is None:
            edit_out = shot["data"]["fend"]
    except KeyError:
        cmds.warning("No edit information found for %s" % shot["name"])
        return

    fps = {
        "12": "12fps",
        "15": "game",
        "16": "16fps",
        "24": "film",
        "25": "pal",
        "30": "ntsc",
        "48": "show",
        "50": "palf",
        "60": "ntscf"
    }.get(api.Session.get("AVALON_FPS"), "pal")  # Default to "pal"

    cmds.currentUnit(time=fps)

    cmds.playbackOptions(minTime=edit_in)
    cmds.playbackOptions(maxTime=edit_out)
    cmds.playbackOptions(animationStartTime=edit_in)
    cmds.playbackOptions(animationEndTime=edit_out)
    cmds.playbackOptions(minTime=edit_in)
    cmds.playbackOptions(maxTime=edit_out)
    cmds.currentTime(edit_in)


def reset_resolution():
    project = io.find_one({"type": "project"})

    try:
        resolution_width = project["data"].get("resolution_width", 1920)
        resolution_height = project["data"].get("resolution_height", 1080)
    except KeyError:
        cmds.warning("No resolution information found for %s"
                     % project["name"])
        return

    cmds.setAttr("defaultResolution.width", resolution_width)
    cmds.setAttr("defaultResolution.height", resolution_height)
