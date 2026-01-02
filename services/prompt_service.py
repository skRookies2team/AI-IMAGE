"""
프롬프트 서비스 모듈
이미지 생성을 위한 프롬프트 정제 및 안전화
"""

from logger import setup_logger
from utils.sensitive_filter import pre_filter_sensitive_words

logger = setup_logger()


async def sanitize_prompt_for_imagen(prompt: str) -> str:
    """
    프롬프트를 Imagen 정책에 맞게 안전하게 변환

    민감하거나 정책 위반 가능성이 있는 표현을 예술적이고 안전한 표현으로 자동 변환합니다.
    사전 필터링을 통해 알려진 민감 단어를 치환합니다.

    Args:
        prompt: 원본 프롬프트

    Returns:
        정제된 안전한 프롬프트
    """
    try:
        # 사전 필터링 (알려진 민감 단어 치환)
        sanitized_prompt = pre_filter_sensitive_words(prompt)

        logger.info("프롬프트 사전 필터링 완료")
        logger.info(f"   원본: {prompt[:100]}...")
        logger.info(f"   정제: {sanitized_prompt[:100]}...")

        return sanitized_prompt

    except Exception as e:
        logger.warning(f"프롬프트 정제 중 오류 발생: {e}")
        logger.info("   원본 프롬프트를 그대로 사용합니다.")
        return prompt
