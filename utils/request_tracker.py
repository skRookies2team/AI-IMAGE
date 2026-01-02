"""
중복 요청 방지 모듈
동일한 요청이 동시에 처리되는 것을 방지
"""

import hashlib
from datetime import datetime
from typing import Dict, Optional

from logger import setup_logger

logger = setup_logger()

# 진행 중인 요청 추적 (중복 방지용)
# 구조: {request_id: {"task": asyncio.Task, "timestamp": datetime, "s3_key": str}}
_processing_requests: Dict[str, Dict] = {}

# 요청 정리 주기 (초) - 오래된 완료된 요청 자동 정리
CLEANUP_INTERVAL = 300  # 5분


def get_processing_requests() -> Dict[str, Dict]:
    """현재 처리 중인 요청 딕셔너리 반환"""
    return _processing_requests


def get_request_id(
    story_id: str,
    s3_key: Optional[str] = None,
    user_prompt: Optional[str] = None
) -> str:
    """
    요청 ID 생성 (중복 방지용)

    노드별 이미지 생성: 각 노드는 다른 s3_key를 가지므로 다른 request_id 생성됨 (정상)
    썸네일 생성: 같은 story_id + 같은 s3_key로 여러 번 호출되면 같은 request_id (중복 차단)

    Args:
        story_id: 스토리 ID
        s3_key: S3 키 (선택사항)
        user_prompt: 사용자 프롬프트 (선택사항)

    Returns:
        16자리 해시된 요청 ID
    """
    # s3_key가 있으면 그것을 기준으로 (가장 정확한 중복 방지)
    if s3_key:
        key = f"{story_id}:{s3_key}"
    elif user_prompt:
        # user_prompt 기반 (같은 프롬프트로 여러 번 호출 방지)
        key = f"{story_id}:{hashlib.md5(user_prompt.encode()).hexdigest()[:8]}"
    else:
        # 타임스탬프 기반 (항상 다른 ID)
        key = f"{story_id}:{datetime.now().isoformat()}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def cleanup_old_requests():
    """완료된 오래된 요청 정리"""
    current_time = datetime.now()
    to_remove = []

    for request_id, request_info in _processing_requests.items():
        task = request_info.get("task")
        timestamp = request_info.get("timestamp")

        # 완료된 작업이거나 5분 이상 지난 요청 제거
        if task and task.done():
            to_remove.append(request_id)
        elif timestamp and (current_time - timestamp).total_seconds() > CLEANUP_INTERVAL:
            to_remove.append(request_id)

    for request_id in to_remove:
        if request_id in _processing_requests:
            del _processing_requests[request_id]
            logger.debug(f"오래된 요청 정리: Request ID {request_id}")


def register_request(request_id: str, task, s3_key: Optional[str], story_id: str):
    """요청 등록"""
    _processing_requests[request_id] = {
        "task": task,
        "timestamp": datetime.now(),
        "s3_key": s3_key,
        "story_id": story_id
    }


def unregister_request(request_id: str):
    """요청 등록 해제"""
    if request_id in _processing_requests:
        del _processing_requests[request_id]


def is_request_processing(request_id: str) -> bool:
    """요청이 처리 중인지 확인"""
    if request_id not in _processing_requests:
        return False

    request_info = _processing_requests[request_id]
    task = request_info.get("task")

    return task and not task.done()
