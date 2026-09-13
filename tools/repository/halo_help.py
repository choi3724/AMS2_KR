"""Restore the reviewed halo-help visibility and translation binding in both menus."""
import hashlib
import struct

import ams2_bgui_editor as bgui

MENUS = {'gui/menu_mainmenu_1_6.bgui', 'gui/menu_ingamemenu_1_6.bgui'}


def record(data):
    nodes = bgui._find_named_nodes(data, 'HideHaloMeshes')
    assert len(nodes) == 1, 'Halo option structure changed'
    matches = [r for r in bgui.parse_text_records(data)
               if nodes[0].start < r.start < nodes[0].start + 8000 and r.position == (16.0, 32.0)]
    assert len(matches) == 1, 'Halo help record changed'
    return matches[0]


def patch(data):
    r = record(data)
    style, reference = r.start + 57, r.flags_offset + 8
    before = (data[style], struct.unpack_from('<I', data, reference)[0])
    if before == (3, 0x552CADF8):
        return data, {}  # Already restored in the reviewed legacy main menu.
    assert before == (19, 0xE0B842FA), ('Unreviewed halo help fields', before)
    fingerprint = hashlib.sha256(data[r.start:r.font_length_offset]).hexdigest().upper()
    rule = {str(r.object_id): [fingerprint, '19', '3', 'E0B842FA', '552CADF8']}
    output = bytearray(data)
    output[style] = 3
    struct.pack_into('<I', output, reference, 0x552CADF8)
    allowed = {style, *range(reference, reference + 4)}
    assert {i for i, (a, b) in enumerate(zip(data, output)) if a != b} <= allowed
    assert len(output) == len(data)
    return bytes(output), rule
