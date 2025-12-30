"""
로깅 설정 모듈
애플리케이션 전역 로깅 설정 및 관리
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime

# 로그 디렉토리
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True, parents=True)

# 로그 파일 경로
LOG_FILE = LOG_DIR / f"ai-image-{datetime.now().strftime('%Y%m%d')}.log"
ERROR_LOG_FILE = LOG_DIR / f"ai-image-error-{datetime.now().strftime('%Y%m%d')}.log"


def setup_logger(name: str = "ai-image", level: str = "INFO") -> logging.Logger:
    """
    로거 설정 및 반환
    
    Args:
        name: 로거 이름
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        설정된 로거 인스턴스
    """
    logger = logging.getLogger(name)
    
    # 이미 핸들러가 설정되어 있으면 기존 로거 반환
    if logger.handlers:
        return logger
    
    # 로그 레벨 설정
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # 로거가 상위로 전파되지 않도록 설정
    logger.propagate = False
    
    # 포맷터 설정
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 콘솔 핸들러 (INFO 이상)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    # 파일 핸들러 (모든 레벨, 회전 로그)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # 에러 전용 파일 핸들러 (ERROR 이상)
    error_file_handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(detailed_formatter)
    logger.addHandler(error_file_handler)
    
    return logger


# 전역 로거 인스턴스
logger = setup_logger()

