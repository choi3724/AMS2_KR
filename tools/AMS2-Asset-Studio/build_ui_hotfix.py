"""Build the reversible 0.7 text-only test overlay outside the repository."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from asset_core import edit_tdb_copy, load_tdb

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HASHES = {
    'text/game.tdb': 'a5110c65582cc517ce09897dac12d3bba4572a219348fcc7a3591417a6fd5fbf',
    'text/drivers.tdb': '9664012afeceb259ac03522908112adb451d51f5e9d9c99f605ed71815fae810',
}
CHANGES = {
    'game.tdb': {
        'Game_HelpText_PhotosAndReplaysSaved': (
            '스티어링이나 스틱 축과 같은 아날로그 컨트롤러 입력으로 메뉴를 조작할 수 있게 합니다.',
            '촬영한 사진과 저장한 리플레이는 드라이버 네트워크의 하이라이트에서 확인할 수 있습니다.',
        ),
        'Game_HelpText_InTheHighlightsSecti': (
            '일반 부착 카메라에 기존 월드 무브먼트 계산 방식을 사용합니다. 이전 카메라 움직임을 선호할 때 켜십시오.',
            '드라이버 네트워크 프로필의 하이라이트에서 저장한 사진과 리플레이를 전체 화면으로 볼 수 있습니다. 프로필에서 저장한 사진과 동영상을 관리하거나 삭제할 수도 있습니다.',
        ),
    },
    'drivers.tdb': {key: ('세이프티\u00a0카', '세이프티 카') for key in (
        'Drivers_Name_SafetyCarDriverPaceCarCamaroSSSCCamaroSSSC',
        'Drivers_Name_SafetyCarDriverPaceCarMiniSCMiniSC',
        'Drivers_Name_SafetyCarDriver',
    )},
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--version', default='0.7-test3')
    args = parser.parse_args()
    source = (args.release_root / 'payload/direct').resolve()
    output = args.output.resolve()
    if output.exists() or output == REPO or REPO in output.parents or source in output.parents:
        raise ValueError('Output must be new and outside the repository/release payload')
    for relative, expected in HASHES.items():
        if sha(source / relative) != expected:
            raise ValueError('Unsupported source hash: ' + relative)
    output.mkdir(parents=True)
    reports = []
    tdb_tool = HERE / 'vendor/ams2_tdb_editor.py'
    for name, changes in CHANGES.items():
        tool, before = load_tdb(source / 'text' / name, tdb_tool)
        edits = {}
        for key, (old, new) in changes.items():
            assert before.keys.count(key) == 1
            index = before.keys.index(key)
            assert before.language('Korean').values[index] == old
            assert tool.validate_token_preservation(before.language('English').values[index], new)['status'] == 'PASS'
            edits[index] = new
        target = output / 'payload/text' / name
        report = edit_tdb_copy(source / 'text' / name, target, tdb_tool, edits)
        _, after = load_tdb(target, tdb_tool)
        for language in before.languages:
            expected = list(language.values)
            if language.name == 'Korean':
                for index, value in edits.items():
                    expected[index] = value
            assert after.language(language.name).values == expected
            assert after.language(language.name).hashes == language.hashes
        reports.append(report)
    manifest = {'version': args.version, 'status': 'AWAITING_GAME_TEST', 'scope': 'TEXT_ONLY',
                'files': [{'path': p, 'before_sha256': h, 'after_sha256': sha(output / 'payload' / p)} for p, h in HASHES.items()],
                'validation': reports}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: 5 Korean TDB values; all other values and hashes preserved; game test required')


if __name__ == '__main__':
    main()
