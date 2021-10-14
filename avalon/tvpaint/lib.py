import os
import tempfile

from . import CommunicationWrapper


def execute_george(george_script):
    return CommunicationWrapper.execute_george(george_script)


def execute_george_through_file(george_script):
    """Execute george script with temp file.

    Allows to execute multiline george script without stopping websocket
    client.

    On windows make sure script does not contain paths with backwards
    slashes in paths, TVPaint won't execute properly in that case.

    Args:
        george_script (str): George script to execute. May be multilined.
    """
    return CommunicationWrapper.execute_george_through_file(george_script)


def parse_layers_data(data):
    layers = []
    layers_raw = data.split("\n")
    for layer_raw in layers_raw:
        layer_raw = layer_raw.strip()
        if not layer_raw:
            continue
        (
            layer_id, group_id, visible, position, opacity, name,
            layer_type,
            frame_start, frame_end, prelighttable, postlighttable,
            selected, editable, sencil_state
        ) = layer_raw.split("|")
        layer = {
            "layer_id": int(layer_id),
            "group_id": int(group_id),
            "visible": visible == "ON",
            "position": int(position),
            "opacity": int(opacity),
            "name": name,
            "type": layer_type,
            "frame_start": int(frame_start),
            "frame_end": int(frame_end),
            "prelighttable": prelighttable == "1",
            "postlighttable": postlighttable == "1",
            "selected": selected == "1",
            "editable": editable == "1",
            "sencil_state": sencil_state
        }
        layers.append(layer)
    return layers


def layers_data(layer_ids=None):
    output_file = tempfile.NamedTemporaryFile(
        mode="w", prefix="a_tvp_", suffix=".txt", delete=False
    )
    output_file.close()
    if layer_ids is not None and isinstance(layer_ids, int):
        layer_ids = [layer_ids]

    output_filepath = output_file.name.replace("\\", "/")
    george_script_lines = [
        # Variable containing full path to output file
        "output_path = \"{}\"".format(output_filepath),
        # Get Current Layer ID
        "tv_LayerCurrentID",
        "current_layer_id = result"
    ]
    # Script part for getting and storing layer information to temp
    layer_data_getter = (
        # Get information about layer's group
        "tv_layercolor \"get\" layer_id",
        "group_id = result",
        "tv_LayerInfo layer_id",
        (
            "PARSE result visible position opacity name"
            " type startFrame endFrame prelighttable postlighttable"
            " selected editable sencilState"
        ),
        # Check if layer ID match `tv_LayerCurrentID`
        "IF CMP(current_layer_id, layer_id)==1",
        # - mark layer as selected if layer id match to current layer id
        "selected=1",
        "END",
        # Prepare line with data separated by "|"
        (
            "line = layer_id'|'group_id'|'visible'|'position'|'opacity'|'"
            "name'|'type'|'startFrame'|'endFrame'|'prelighttable'|'"
            "postlighttable'|'selected'|'editable'|'sencilState"
        ),
        # Write data to output file
        "tv_writetextfile \"strict\" \"append\" '\"'output_path'\"' line",
    )

    # Collect data for all layers if layers are not specified
    if layer_ids is None:
        george_script_lines.extend((
            # Layer loop variables
            "loop = 1",
            "idx = 0",
            # Layers loop
            "WHILE loop",
            "tv_LayerGetID idx",
            "layer_id = result",
            "idx = idx + 1",
            # Stop loop if layer_id is "NONE"
            "IF CMP(layer_id, \"NONE\")==1",
            "loop = 0",
            "ELSE",
            *layer_data_getter,
            "END",
            "END"
        ))
    else:
        for layer_id in layer_ids:
            george_script_lines.append("layer_id = {}".format(layer_id))
            george_script_lines.extend(layer_data_getter)

    george_script = "\n".join(george_script_lines)
    execute_george_through_file(george_script)

    with open(output_filepath, "r") as stream:
        data = stream.read()

    output = parse_layers_data(data)
    os.remove(output_filepath)
    return output


def parse_group_data(data):
    output = []
    groups_raw = data.split("\n")
    for group_raw in groups_raw:
        group_raw = group_raw.strip()
        if not group_raw:
            continue

        parts = group_raw.split(" ")
        # Check for length and concatenate 2 last items until length match
        # - this happens if name contain spaces
        while len(parts) > 6:
            last_item = parts.pop(-1)
            parts[-1] = " ".join([parts[-1], last_item])
        clip_id, group_id, red, green, blue, name = parts

        group = {
            "group_id": int(group_id),
            "name": name,
            "clip_id": int(clip_id),
            "red": int(red),
            "green": int(green),
            "blue": int(blue),
        }
        output.append(group)
    return output


def groups_data():
    output_file = tempfile.NamedTemporaryFile(
        mode="w", prefix="a_tvp_", suffix=".txt", delete=False
    )
    output_file.close()

    output_filepath = output_file.name.replace("\\", "/")
    george_script_lines = (
        # Variable containing full path to output file
        "output_path = \"{}\"".format(output_filepath),
        "loop = 1",
        "FOR idx = 1 TO 12",
        "tv_layercolor \"getcolor\" 0 idx",
        "tv_writetextfile \"strict\" \"append\" '\"'output_path'\"' result",
        "END"
    )
    george_script = "\n".join(george_script_lines)
    execute_george_through_file(george_script)

    with open(output_filepath, "r") as stream:
        data = stream.read()

    output = parse_group_data(data)
    os.remove(output_filepath)
    return output


def get_layers_pre_post_behavior(layer_ids):
    """Collect data about pre and post behavior of layer ids.

    Pre and Post behaviors is enumerator of possible values:
    - "none"
    - "repeat"
    - "pingpong"
    - "hold"

    Example output:
    ```json
    {
        0: {
            "pre": "none",
            "post": "loop"
        }
    }
    ```

    Returns:
        dict: Key is layer id value is dictionary with "pre" and "post" keys.
    """
    # Skip if is empty
    if not layer_ids:
        return {}

    # Auto convert to list
    if not isinstance(layer_ids, (list, set, tuple)):
        layer_ids = [layer_ids]

    # Prepare temp file
    output_file = tempfile.NamedTemporaryFile(
        mode="w", prefix="a_tvp_", suffix=".txt", delete=False
    )
    output_file.close()

    output_filepath = output_file.name.replace("\\", "/")
    george_script_lines = [
        # Variable containing full path to output file
        "output_path = \"{}\"".format(output_filepath),
    ]
    for layer_id in layer_ids:
        george_script_lines.extend([
            "layer_id = {}".format(layer_id),
            "tv_layerprebehavior layer_id",
            "pre_beh = result",
            "tv_layerpostbehavior layer_id",
            "post_beh = result",
            "line = layer_id'|'pre_beh'|'post_beh",
            "tv_writetextfile \"strict\" \"append\" '\"'output_path'\"' line"
        ])

    george_script = "\n".join(george_script_lines)
    execute_george_through_file(george_script)

    # Read data
    with open(output_filepath, "r") as stream:
        data = stream.read()

    # Remove temp file
    os.remove(output_filepath)

    # Parse data
    output = {}
    raw_lines = data.split("\n")
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) != 3:
            continue
        layer_id, pre_beh, post_beh = parts
        output[int(layer_id)] = {
            "pre": pre_beh.lower(),
            "post": post_beh.lower()
        }
    return output


def get_exposure_frames(layer_id, first_frame=None, last_frame=None):
    """Get exposure frames.

    Easily said returns frames where keyframes are. Recognized with george
    function `tv_exposureinfo` returning "Head".

    Args:
        layer_id (int): Id of a layer for which exposure frames should
            look for.
        first_frame (int): From which frame will look for exposure frames.
            Used layers first frame if not entered.
        last_frame (int): Last frame where will look for exposure frames.
            Used layers last frame if not entered.

    Returns:
        list: Frames where exposure is set to "Head".
    """
    if first_frame is None or last_frame is None:
        layer = layers_data(layer_id)[0]
        if first_frame is None:
            first_frame = layer["frame_start"]
        if last_frame is None:
            last_frame = layer["frame_end"]

    tmp_file = tempfile.NamedTemporaryFile(
        mode="w", prefix="a_tvp_", suffix=".txt", delete=False
    )
    tmp_file.close()
    tmp_output_path = tmp_file.name.replace("\\", "/")
    george_script_lines = [
        "tv_layerset {}".format(layer_id),
        "output_path = \"{}\"".format(tmp_output_path),
        "output = \"\"",
        "frame = {}".format(first_frame),
        "WHILE (frame <= {})".format(last_frame),
        "tv_exposureinfo frame",
        "exposure = result",
        "IF (CMP(exposure, \"Head\") == 1)",
        "IF (CMP(output, \"\") == 1)",
        "output = output''frame",
        "ELSE",
        "output = output'|'frame",
        "END",
        "END",
        "frame = frame + 1",
        "END",
        "tv_writetextfile \"strict\" \"append\" '\"'output_path'\"' output"
    ]

    execute_george_through_file("\n".join(george_script_lines))

    with open(tmp_output_path, "r") as stream:
        data = stream.read()

    os.remove(tmp_output_path)

    lines = []
    for line in data.split("\n"):
        line = line.strip()
        if line:
            lines.append(line)

    exposure_frames = []
    for line in lines:
        for frame in line.split("|"):
            exposure_frames.append(int(frame))
    return exposure_frames
