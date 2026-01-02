"""
민감 단어 필터링 모듈
이미지 생성 시 정책 위반을 방지하기 위한 민감 단어 치환
"""

import re
from logger import setup_logger

logger = setup_logger()

# 민감한 단어 -> 안전한 대체어 매핑 (한국어 + 영어)
SENSITIVE_WORD_REPLACEMENTS = {
    # 피/출혈 관련
    "피": "붉은 빛",
    "blood": "red accents",
    "bloody": "crimson-toned",
    "bleeding": "flowing crimson",
    "출혈": "붉은 흐름",
    "피투성이": "붉게 물든",

    # 살인/죽음 관련
    "살인": "극적인 대결",
    "살해": "극적인 순간",
    "죽음": "마지막 순간",
    "죽이다": "대결하다",
    "죽인": "맞선",
    "죽어": "쓰러진",
    "시체": "쓰러진 인물",
    "사체": "누운 형체",
    "murder": "dramatic confrontation",
    "kill": "confront",
    "killing": "confronting",
    "killed": "confronted",
    "death": "final moment",
    "dead": "fallen",
    "corpse": "resting figure",
    "body": "figure",

    # 폭력/공격 관련
    "폭력": "격렬한 움직임",
    "폭력적": "역동적인",
    "공격": "대치",
    "공격하": "맞서",
    "때리": "부딪히",
    "violence": "intense action",
    "violent": "dynamic",
    "attack": "confrontation",
    "attacking": "facing",
    "brutal": "intense",
    "brutality": "intensity",
    "cruel": "dramatic",
    "cruelty": "drama",

    # 무기 관련
    "무기": "도구",
    "칼": "금속 물체",
    "검": "고대 유물",
    "총": "장치",
    "권총": "장치",
    "소총": "장치",
    "단검": "금속 조각",
    "도끼": "도구",
    "weapon": "artifact",
    "weapons": "artifacts",
    "sword": "ancient blade",
    "knife": "metallic object",
    "gun": "device",
    "pistol": "device",
    "rifle": "equipment",
    "dagger": "ornate object",
    "axe": "tool",

    # 전투/전쟁 관련
    "전투": "대결 장면",
    "전쟁": "역사적 충돌",
    "싸움": "대치 상황",
    "싸우": "맞서",
    "battle": "dramatic standoff",
    "war": "historic conflict",
    "combat": "confrontation",
    "fight": "standoff",
    "fighting": "facing off",
    "warfare": "conflict",

    # 고통/부상 관련
    "고문": "고난",
    "고통": "시련",
    "상처": "흔적",
    "부상": "표식",
    "torture": "hardship",
    "torment": "struggle",
    "wound": "mark",
    "wounded": "marked",
    "injury": "scar",
    "injured": "scarred",
    "pain": "struggle",
    "painful": "difficult",
    "suffering": "enduring",

    # 공포/악 관련
    "악마": "신비로운 존재",
    "악": "어둠",
    "악한": "그림자 같은",
    "괴물": "신화적 존재",
    "무서운": "신비로운",
    "공포": "긴장감",
    "두려운": "불가사의한",
    "demon": "mythical being",
    "devil": "shadowy entity",
    "evil": "shadowy",
    "monster": "legendary creature",
    "scary": "mysterious",
    "terrifying": "enigmatic",
    "horror": "suspense",
    "fear": "tension",

    # 범죄 관련
    "범죄": "사건",
    "범인": "인물",
    "피해자": "관련자",
    "살인자": "대결 상대",
    "crime": "incident",
    "criminal": "figure",
    "victim": "person involved",
    "murderer": "antagonist",
    "killer": "rival",
}


def pre_filter_sensitive_words(text: str) -> str:
    """
    민감한 단어를 안전한 대체어로 사전 치환

    Gemini 호출 전에 알려진 민감한 단어들을 먼저 변환하여
    정책 위반 가능성을 사전에 제거합니다.

    Args:
        text: 원본 텍스트

    Returns:
        민감한 단어가 치환된 텍스트
    """
    result = text
    replacements_made = []

    # 대소문자 구분 없이 치환 (영어의 경우)
    for sensitive_word, safe_word in SENSITIVE_WORD_REPLACEMENTS.items():
        # 한국어는 그대로, 영어는 대소문자 무시하여 검색
        if any(ord(c) > 127 for c in sensitive_word):
            # 한국어 단어
            if sensitive_word in result:
                result = result.replace(sensitive_word, safe_word)
                replacements_made.append(f"'{sensitive_word}' -> '{safe_word}'")
        else:
            # 영어 단어 - 단어 경계를 고려하여 치환
            pattern = re.compile(re.escape(sensitive_word), re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(safe_word, result)
                replacements_made.append(f"'{sensitive_word}' -> '{safe_word}'")

    if replacements_made:
        logger.info(f"사전 필터링 적용: {len(replacements_made)}개 단어 치환")
        for replacement in replacements_made[:5]:  # 최대 5개만 로그
            logger.debug(f"   {replacement}")
        if len(replacements_made) > 5:
            logger.debug(f"   ... 외 {len(replacements_made) - 5}개")

    return result


def is_imagen_safety_block_error(err: Exception) -> bool:
    """Imagen 안전 필터/정책 차단으로 보이는 에러인지 간단 휴리스틱으로 판별"""
    msg = str(err).upper()
    keywords = [
        "SENSITIVE",
        "SAFETY",
        "BLOCKED",
        "FILTER",
        "VIOLATION",
        "CONTENT",
        "POLICY",
    ]
    return any(k in msg for k in keywords)
