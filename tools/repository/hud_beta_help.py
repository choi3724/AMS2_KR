"""Translate the inline UTF-16 HUD beta help without changing other menu fields."""
import struct

import ams2_bgui_editor as bgui

MENU = 'gui/menu_mainmenu_1_6.bgui'
ENGLISH = 'Enables the public beta of the new work-in-progress HUD.\r\n\r\nSome elements may be incomplete, missing user customisation options, or be missing entirely. Despite this the beta HUD should be in a useable state and feedback is welcome.'
KOREAN = '개발 중인 새 HUD의 공개 베타를 사용합니다.\r\n\r\n일부 요소가 미완성이거나 사용자 설정 옵션 및 기능이 빠져 있을 수 있습니다. 베타 HUD는 사용 가능한 수준이며, 여러분의 의견을 환영합니다.'
LEGACY_KOREAN = ('개발 중인 새 HUD의 공개 베타를 사용합니다.' + ' ' * 30 + '\r\n\r\n'
                 '일부 요소가 미완성이거나 사용자 설정 옵션이 없거나 표시되지 않을 수 있습니다. 현재도 사용할 수 있으며 피드백을 환영합니다.' + ' ' * 102)


def field(text):
    encoded = text.encode('utf-16-le')
    return struct.pack('<I', len(encoded) // 2) + encoded


def patch(data):
    matches = [field(text) for text in (ENGLISH, LEGACY_KOREAN) if field(text) in data]
    after = field(KOREAN)
    if len(matches) != 1 or data.count(matches[0]) != 1 or after in data:
        raise ValueError('HUD beta help literal changed; review the source menu')
    before = matches[0]
    output = data.replace(before, after, 1)
    assert output.replace(after, before, 1) == data
    assert bgui.parse_resource_header(output) == bgui.parse_resource_header(data)
    assert [r.semantic() for r in bgui.parse_text_records(output)] == [r.semantic() for r in bgui.parse_text_records(data)]
    return output
