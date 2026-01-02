"""
스타일 서비스 모듈
소설 스타일 분석, 저장, 로드 및 프롬프트 생성
"""

import json
from typing import Optional, Dict
from pathlib import Path
from datetime import datetime

from config import config
from logger import setup_logger
from services.gemini_service import get_model

logger = setup_logger()


def get_style_file_path(story_id: str) -> Path:
    """스타일 파일 경로 반환"""
    return config.STYLES_DIR / f"{story_id}.json"


def save_novel_style(story_id: str, style_data: Dict):
    """소설 스타일을 파일로 저장"""
    style_file = get_style_file_path(story_id)
    style_data['story_id'] = story_id
    style_data['updated_at'] = datetime.now().isoformat()

    with open(style_file, 'w', encoding='utf-8') as f:
        json.dump(style_data, f, ensure_ascii=False, indent=2)

    return style_file


def load_novel_style(story_id: str) -> Optional[Dict]:
    """소설 스타일 로드"""
    style_file = get_style_file_path(story_id)
    if not style_file.exists():
        return None

    with open(style_file, 'r', encoding='utf-8') as f:
        return json.load(f)


async def analyze_novel_style(novel_text: str, title: Optional[str] = None) -> Dict:
    """
    Gemini를 사용하여 소설의 스타일과 분위기를 분석

    Returns:
        분석된 스타일 정보 (분위기, 시각적 스타일, 이미지 생성용 키워드 등)
    """
    # 소설 텍스트의 일부만 사용 (너무 길면 토큰 제한)
    text_sample = novel_text[:5000] if len(novel_text) > 5000 else novel_text

    prompt = f"""Analyze the style and atmosphere of the following novel for image generation purposes.

NOVEL TITLE: {title if title else "Untitled"}

NOVEL CONTENT (excerpt):
{text_sample}

Provide a JSON response with the following structure. All values should be optimized for AI image generation:

{{
    "style_summary": "2-3 sentences describing the overall style and tone of the novel",
    "atmosphere": "Atmosphere description in English (e.g., 'dark and mysterious', 'bright and cheerful', 'melancholic and poetic')",
    "visual_style": "Visual art style for image generation (e.g., 'dark fantasy art', 'realistic illustration', 'anime style', 'oil painting style')",
    "key_themes": ["theme1", "theme2", "theme3"],
    "color_palette": "Color palette description (e.g., 'cool blue tones with purple accents', 'warm golden hues', 'high contrast dark and light')",
    "lighting_style": "Lighting style for images (e.g., 'dramatic chiaroscuro', 'soft diffused light', 'moonlit ambiance', 'golden hour warmth')",
    "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}}

IMPORTANT for visual_keywords:
- Provide 5-8 English keywords that can be directly used in image generation prompts
- Include: art style, mood, setting type, time of day, weather/atmosphere
- Examples: "fantasy", "medieval", "misty forest", "twilight", "ethereal glow", "gothic architecture"
- These keywords should be safe for image generation (avoid violent or sensitive terms)

Respond ONLY with valid JSON, no additional text or markdown."""

    try:
        # Vertex AI GenerativeModel 사용
        model_instance = get_model()
        response = model_instance.generate_content(prompt)

        # 응답 텍스트 추출
        if hasattr(response, 'text'):
            response_text = response.text.strip()
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            response_text = response.candidates[0].content.parts[0].text.strip()
        else:
            raise ValueError("응답에서 텍스트를 추출할 수 없습니다.")

        # JSON 응답 파싱
        # JSON 코드 블록이 있으면 제거
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        style_data = json.loads(response_text)

        # 필수 필드 확인 및 기본값 설정
        if 'lighting_style' not in style_data:
            style_data['lighting_style'] = 'natural lighting'
        if 'visual_keywords' not in style_data:
            style_data['visual_keywords'] = []

        return style_data
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 오류: {e}")
        logger.debug(f"응답 텍스트: {response_text[:200]}")
        # 기본값 반환
        return {
            "style_summary": "Unable to analyze novel style.",
            "atmosphere": "general",
            "visual_style": "realistic illustration",
            "key_themes": [],
            "color_palette": "natural colors",
            "lighting_style": "natural lighting",
            "visual_keywords": ["illustration", "detailed", "atmospheric"]
        }
    except Exception as e:
        logger.error(f"스타일 분석 오류: {e}", exc_info=True)
        # 기본값 반환
        return {
            "style_summary": "Unable to analyze novel style.",
            "atmosphere": "general",
            "visual_style": "realistic illustration",
            "key_themes": [],
            "color_palette": "natural colors",
            "lighting_style": "natural lighting",
            "visual_keywords": ["illustration", "detailed", "atmospheric"]
        }


async def generate_thumbnail_prompt(
    title: Optional[str],
    novel_style: Dict,
    novel_text_sample: Optional[str] = None
) -> str:
    """
    소설 썸네일 이미지를 위한 프롬프트 생성
    """
    # 시각적 키워드 추출
    visual_keywords = novel_style.get('visual_keywords', [])
    visual_keywords_str = ", ".join(visual_keywords) if visual_keywords else ""

    style_context = f"""
- Atmosphere: {novel_style.get('atmosphere', 'general')}
- Visual Style: {novel_style.get('visual_style', 'realistic style')}
- Color Palette: {novel_style.get('color_palette', 'natural colors')}
- Key Themes: {', '.join(novel_style.get('key_themes', [])[:3])}
- Lighting: {novel_style.get('lighting_style', 'natural lighting')}
- Visual Keywords: {visual_keywords_str}
"""

    text_sample = f"\nNovel excerpt: {novel_text_sample[:300]}" if novel_text_sample else ""

    prompt = f"""You are an expert book cover designer and image prompt engineer.

NOVEL TITLE: {title if title else "Untitled"}

NOVEL STYLE INFORMATION:
{style_context}{text_sample}

CREATE a book cover/thumbnail image prompt that:

1. COMPOSITION:
   - Strong focal point that captures the novel's essence
   - Suitable for vertical format (book cover style)
   - Clear visual hierarchy with a central element
   - Leave space for potential title overlay (but don't include text)

2. VISUAL ELEMENTS:
   - Incorporate symbolic elements from the novel's themes
   - Use the specified color palette and atmosphere
   - Add atmospheric effects (mist, light rays, particles) if appropriate

3. STYLE REQUIREMENTS:
   - Art style matching the novel's genre
   - Professional book cover quality
   - Must include: "book cover art", "professional illustration"
   - Add: "highly detailed", "cinematic composition", "dramatic lighting"

4. SAFETY COMPLIANCE:
   - Use artistic/symbolic representation for any dramatic themes
   - Focus on atmosphere and mood rather than explicit content
   - Transform any potentially sensitive elements into abstract visuals

5. FORMAT:
   - Write in English only
   - Keep between 80-120 words
   - Do NOT include any text/typography in the image description

OUTPUT: Write ONLY the prompt. No explanations, no quotes.

THUMBNAIL PROMPT:"""

    try:
        model_instance = get_model()
        response = model_instance.generate_content(prompt)

        if hasattr(response, 'text'):
            thumbnail_prompt = response.text.strip()
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            thumbnail_prompt = response.candidates[0].content.parts[0].text.strip()
        else:
            raise ValueError("응답에서 텍스트를 추출할 수 없습니다.")

        # 따옴표로 감싸져 있으면 제거
        if thumbnail_prompt.startswith('"') and thumbnail_prompt.endswith('"'):
            thumbnail_prompt = thumbnail_prompt[1:-1]
        if thumbnail_prompt.startswith("'") and thumbnail_prompt.endswith("'"):
            thumbnail_prompt = thumbnail_prompt[1:-1]

        return thumbnail_prompt
    except Exception as e:
        logger.error(f"썸네일 프롬프트 생성 오류: {e}", exc_info=True)
        # 기본 프롬프트 반환
        return f"Book cover illustration for '{title or 'a novel'}', {novel_style.get('visual_style', 'realistic style')}, {novel_style.get('atmosphere', 'atmospheric')} mood, {novel_style.get('color_palette', 'natural colors')}, professional artwork, highly detailed, cinematic lighting, dramatic composition"


async def generate_enhanced_prompt(
    user_prompt: str,
    novel_style: Dict,
    context_text: Optional[str] = None
) -> str:
    """
    사용자 프롬프트와 소설 스타일을 결합하여 최종 이미지 생성 프롬프트 생성
    """
    # 스타일 정보에서 시각적 키워드 추출
    visual_keywords = novel_style.get('visual_keywords', [])
    visual_keywords_str = ", ".join(visual_keywords) if visual_keywords else ""

    style_context = f"""
- Atmosphere: {novel_style.get('atmosphere', 'general')}
- Visual Style: {novel_style.get('visual_style', 'realistic style')}
- Color Palette: {novel_style.get('color_palette', 'natural colors')}
- Lighting: {novel_style.get('lighting_style', 'natural lighting')}
- Visual Keywords: {visual_keywords_str}
"""

    context = f"\nAdditional Context: {context_text[:500]}" if context_text else ""

    prompt = f"""You are an expert image generation prompt engineer. Create a high-quality image generation prompt.

USER'S REQUEST: {user_prompt}

NOVEL STYLE INFORMATION:
{style_context}{context}

REQUIREMENTS:
1. Maintain the user's original intent and subject matter
2. Naturally incorporate the novel's atmosphere and visual style
3. Structure the prompt as follows:
   - Main subject with specific details
   - Environment/background description
   - Lighting and mood (use novel's atmosphere)
   - Art style and quality keywords

4. MUST include these quality enhancers:
   - Art style: "digital painting", "concept art", or "illustration"
   - Quality: "highly detailed", "professional artwork", "masterpiece"
   - Technical: "8k resolution", "sharp focus", "intricate details"

5. Use cinematic/artistic language:
   - Instead of "dark" -> "dramatic shadows", "low-key lighting"
   - Instead of "scary" -> "mysterious atmosphere", "enigmatic mood"
   - Instead of "fighting" -> "dynamic pose", "intense moment"

6. Keep the prompt between 80-150 words
7. Write in English only
8. Do NOT include any negative words or things to avoid

OUTPUT: Write ONLY the enhanced prompt. No explanations, no quotes, no prefixes.

ENHANCED PROMPT:"""

    try:
        # Vertex AI GenerativeModel 사용
        model_instance = get_model()
        response = model_instance.generate_content(prompt)

        # 응답 텍스트 추출
        if hasattr(response, 'text'):
            enhanced_prompt = response.text.strip()
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            enhanced_prompt = response.candidates[0].content.parts[0].text.strip()
        else:
            raise ValueError("응답에서 텍스트를 추출할 수 없습니다.")

        # 따옴표로 감싸져 있으면 제거
        if enhanced_prompt.startswith('"') and enhanced_prompt.endswith('"'):
            enhanced_prompt = enhanced_prompt[1:-1]
        if enhanced_prompt.startswith("'") and enhanced_prompt.endswith("'"):
            enhanced_prompt = enhanced_prompt[1:-1]

        return enhanced_prompt
    except Exception as e:
        logger.error(f"프롬프트 개선 오류: {e}", exc_info=True)
        # 오류 발생 시 사용자 프롬프트 그대로 반환
        return user_prompt
