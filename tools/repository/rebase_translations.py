"""Rebase Korean overlays onto extracted, verified Steam BOOTFLOW tables."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'AMS2-Asset-Studio/vendor'))
import ams2_tdb_editor as tdb

STOCK_HASHES = {
    'career.tdb': '04168c8efee1b5c8a367dc9ad27625f3b34193f8a57bfeb32827c9db37a0f887',
    'drivers.tdb': '9b17bc29c721123a96feb9bc9baf2888f27baf020808bfc571f469bb391043b1',
    'game.tdb': '2f8597681c4e3846df9bfa4747f1f613124aa3caba52ac106cb24b742d87287a',
    'general.tdb': '7471019c95862d7542fd44b1d176f53abd6cbe1cacb21eeb52e03b51fbb786bf',
    'online.tdb': 'e6b383ebbd1750e16e185a30d5538744a11d484790fce39e199fb970fc7497b3',
    'pit.tdb': '730ba9b98ea731633d3662cc0b32f491dc5659bd4da93702a488ce1f6850c2ae',
    'platform.tdb': 'b9c10008179161f7f0a74af401e8339031698087c35c8040d19601b3e9a8a49a',
    'presence.tdb': '860529f123bff9a48f4359959c10bc35a3849f61e70ca5c622201f92e43a154b',
    'rac.tdb': 'cd442fa1580a987166cd87765a28ad38fe7ad00a9d711003f4dc72f67f787aac',
}

# Reviewed against build 25271800. Unknown additions or changed English stop the build.
TRANSLATIONS = {
    'Game_MainMenu_StintLimit': '주행 횟수 제한',
    'Game_MainMenu_LapLimit': '랩 수 제한',
    'Game_InGameMenu_WarnStintLimit': '이번 예선에서는 총 [NUMSTINTS]회 주행할 수 있으며, 주행당 [NUMLAPS]랩으로 제한됩니다.',
    'Game_InGameMenu_WarnStintLimitParcFerme': '이번 예선에서는 총 [NUMSTINTS]회 주행할 수 있으며, 주행당 [NUMLAPS]랩으로 제한됩니다. 예선 종료 시 차량 설정으로 레이스를 시작합니다.',
    'Game_InGameMenu_WarnStintLimitParcFermeWithFuel': '이번 예선에서는 총 [NUMSTINTS]회 주행할 수 있으며, 주행당 [NUMLAPS]랩으로 제한됩니다. 예선 종료 시 차량 설정과 연료량으로 레이스를 시작합니다.',
    'Game_HelpText_LapLimit': '각 드라이버가 이번 세션에서 완료할 수 있는 최대 랩 수를 설정합니다. 피트 진입 랩과 진출 랩도 포함됩니다.\r\n\r\n주행 횟수 제한을 사용하면 랩 수 제한은 세션 전체가 아닌 각 주행에 적용됩니다.\r\n\r\n랩 수 제한을 초과하면 해당 세션에서 실격 처리됩니다.',
    'Game_HelpText_StintLimit': '드라이버가 피트를 나가 트랙을 주행할 수 있는 최대 횟수를 설정합니다. 횟수를 모두 사용하면 차고에서 더 이상 출발할 수 없습니다.\r\n\r\n피트 레인을 통과하거나 차고로 돌아오면 새 주행을 시작할 수 있습니다.\r\n\r\n주행 횟수 제한을 초과하면 해당 세션에서 실격 처리됩니다.',
    'RAC_Controls_TowToPit': '피트로 견인',
    'RAC_UI_Stint': '주행',
    'RAC_UI_Stints': '주행 횟수',
    'Game_UI_OpponentThrottleSkillLower': 'AI 구동력 활용 실력 배율',
    'Game_HelpText_LiveTrackPreset': "젖음이나 고무 누적 여부를 포함해 세션 시작 시 노면 상태를 설정합니다.\r\n\r\n'기본 진행형'이면 이전 세션의 고무 상태를 이어받습니다. 주말 첫 세션이라면 '중간 고무량' 프리셋에서 시작합니다. 다른 설정은 이전 세션 종료 상태와 관계없이 세션 시작 때 해당 프리셋을 적용합니다.\r\n\r\n예: 적은 고무량으로 주말을 시작한 뒤 주행에 따라 이어가려면 연습='고무 적음', 예선='기본 진행형', 레이스='기본 진행형'으로 설정합니다.\r\n\r\n실제 날씨 사용 시 시작 상태가 이벤트 전 실제 날씨로 결정되므로 젖은 노면 프리셋은 사용할 수 없습니다.",
    'Game_HelpText_OpponentThrottleSkill': '주 AI 실력 설정을 기준으로 코너 탈출 구간에서 AI의 성능을 조절합니다. 코너를 빠져나올 때 AI가 너무 빠르거나 느리면 조절하십시오.',
    'Game_HelpText_OpponentBrakeSkill': '주 AI 실력 설정을 기준으로 제동 중 AI의 성능을 조절합니다. AI가 코너에 너무 빠르게 진입하면 조절하십시오.',
    'Game_HelpText_OpponentWetSkill': '주 AI 실력 설정을 기준으로 우천 상태에서 AI의 성능을 조절합니다. 건조 상태에 비해 AI가 너무 빠르거나 느리면 조절하십시오.',
    'Game_HelpText_PrivateQualifyingSession': "'솔로'로 설정하면 슈퍼폴 또는 오벌 방식 예선처럼 각 드라이버가 다른 차량 없이 혼자 주행합니다.\r\n\r\n'같은 클래스'로 설정하면 각 클래스가 다른 클래스의 차량 없이 따로 주행합니다.",
    'Game_CarClasses_FUltimate': 'Formula Ultimate Hybrid Gen2',
    'Game_CarClasses_FUltimateGen2': 'Formula Ultimate Hybrid Gen3',
    'Game_CarClasses_FUltimateGen1': 'Formula Ultimate Hybrid Gen1',
    'General_TrackDetails_Velopark2017STT': '벨로파크 STT',
}
for name, korean in (
    ('AngusWalker', '앵거스 워커'), ('DanielBradley', '대니얼 브래들리'),
    ('DougPorter', '더그 포터'), ('ErwanBertin', '에르완 베르탱'),
    ('FrancisLanglois', '프랑시스 랑글루아'), ('GeoffPrice', '제프 프라이스'),
    ('RemyMorel', '레미 모렐'), ('TomHardy', '톰 하디'),
):
    TRANSLATIONS['Drivers_Name_' + name + 'GT1PANOZGTR1'] = korean


def merge(stock, patch):
    result = copy.deepcopy(stock)
    old = {key: i for i, key in enumerate(patch.keys)}
    # Stock general.tdb repeats one identical entry. Preserve it; reject ambiguous duplicates.
    for document in (stock, patch):
        seen = {}
        for i, key in enumerate(document.keys):
            values = [(language.hashes[i], language.values[i]) for language in document.languages]
            if key in seen and seen[key] != values:
                raise ValueError('Conflicting duplicate translation key: ' + key)
            seen[key] = values
    added, changed = [], []
    for i, key in enumerate(stock.keys):
        english = stock.language('English').values[i]
        previous = old.get(key)
        if previous is None:
            added.append(key)
        elif english != patch.language('English').values[previous]:
            changed.append(key)
        needs_review = previous is None or key in changed
        if needs_review and key not in TRANSLATIONS:
            raise ValueError('Unreviewed new/changed English: ' + key)
        value = TRANSLATIONS[key] if needs_review else patch.language('Korean').values[previous]
        if needs_review and tdb.validate_token_preservation(english, value)['status'] != 'PASS':
            raise ValueError('Translation tokens changed: ' + key)
        result.language('Korean').values[i] = value
    # Keep existing patch-only keys (e.g. track labels) without replacing stock metadata.
    extras = [key for key in patch.keys if key not in set(stock.keys)]
    for key in extras:
        i = old[key]
        result.keys.append(key)
        for language in result.languages:
            source = patch.language(language.name)
            language.hashes.append(source.hashes[i])
            language.values.append(source.values[i])
    result.groups += [group for group in patch.groups if group not in result.groups]
    result.key_count = len(result.keys)
    result.group_count = len(result.groups)
    result.key_string_bytes_with_nuls = sum(len(k.encode('utf-8')) + 1 for k in result.keys)
    result.group_string_bytes_with_nuls = sum(len(k.encode('utf-8')) + 1 for k in result.groups)
    data = tdb.serialize_tdb(result)
    check = tdb.parse_tdb_bytes(data)
    assert check.keys[:stock.key_count] == stock.keys
    for language in stock.languages:
        actual = check.language(language.name)
        assert actual.hashes[:stock.key_count] == language.hashes
        if language.name != 'Korean':
            assert actual.values[:stock.key_count] == language.values
    for i, key in enumerate(stock.keys):
        if key not in added + changed:
            assert check.language('Korean').values[i] == patch.language('Korean').values[old[key]]
    for i, key in enumerate(extras, stock.key_count):
        for language in patch.languages:
            assert check.language(language.name).values[i] == language.values[old[key]]
            assert check.language(language.name).hashes[i] == language.hashes[old[key]]
    return data, {'added': added, 'english_changed': changed, 'patch_only_preserved': extras}


def build(stock_dir, patch_dir, output):
    if output.exists():
        raise ValueError('Use a new translation output directory')
    results, files = [], []
    for source in sorted(patch_dir.glob('*.tdb')):
        native = stock_dir / source.name
        if hashlib.sha256(native.read_bytes()).hexdigest() != STOCK_HASHES.get(source.name):
            raise ValueError('Unreviewed stock table: ' + str(native))
        stock, patch = tdb.parse_tdb(native), tdb.parse_tdb(source)
        data, report = merge(stock, patch)
        report.update(file=source.name, stock_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                      before_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      after_sha256=hashlib.sha256(data).hexdigest())
        files.append((source.name, data))
        results.append(report)
    if not files:
        raise ValueError('No patch translation tables')
    output.mkdir(parents=True)
    for name, data in files:
        (output / name).write_bytes(data)
    (output / 'translation-review.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock', required=True, type=Path)
    parser.add_argument('--patch', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    reports = build(args.stock, args.patch, args.output)
    print('PASS:', len(reports), 'tables; native keys/hashes/non-Korean values and existing translations preserved')
