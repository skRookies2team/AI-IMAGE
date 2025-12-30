"""
실제 이미지 생성 테스트
스토리 텍스트 기반으로 사용자 프롬프트에 따른 이미지 생성 테스트
"""

import requests
import json
import time

# 서버 URL
BASE_URL = "http://localhost:8001"

# 테스트 데이터
STORY_ID = "test-story"
NODE_ID = "test-node"
NOVEL_TEXT = """
그는 어둠 속에서 천천히 걸어갔다. 달빛이 구름 사이로 스며들어와 그의 그림자를 길게 만들었다.
주변은 고요했고, 오직 바람 소리만이 귓가를 스쳤다. 그는 손에 든 등불을 높이 들어 앞을 비췄다.
그곳에는 오래된 성이 서 있었다. 성의 벽은 세월의 흔적이 고스란히 남아있었고,
탑 위에는 까마귀들이 날개를 펼치고 있었다. 성문은 반쯤 열려있었고, 안쪽은 깊은 어둠으로 가득했다.
"""
NOVEL_TITLE = "어둠 속의 성"
USER_PROMPTS = [
    "A knight walking in the dark",
    "An old castle in the moonlight",
    "A mysterious door in the castle"
]

# 프롬프트 정제 기능 테스트를 위한 민감한 프롬프트 (정책 위반 가능성 있음)
SENSITIVE_PROMPTS = [
    "A dramatic battle scene with weapons",
    "An intense emotional confrontation",
    "A tense standoff in the darkness"
]

def print_step(step_num, message):
    """단계 출력"""
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {message}")
    print(f"{'='*60}")

def test_image_generation():
    """이미지 생성 테스트"""
    print("\n" + "="*60)
    print("실제 이미지 생성 테스트")
    print("="*60)
    
    # Step 1: 서버 헬스 체크
    print_step(1, "서버 헬스 체크")
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print("✅ 서버 연결 성공")
        else:
            print(f"❌ 서버 응답 오류: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ 서버 연결 실패: {e}")
        print("   서버를 먼저 실행하세요: python main.py")
        return
    
    # Step 2: 스타일 학습
    print_step(2, "소설 스타일 학습")
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/learn-style",
            json={
                "story_id": STORY_ID,
                "novel_text": NOVEL_TEXT,
                "title": NOVEL_TITLE
            },
            timeout=60
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 스타일 학습 완료")
            print(f"   분위기: {data.get('atmosphere', '')}")
            print(f"   시각적 스타일: {data.get('visual_style', '')}")
        else:
            print(f"❌ 스타일 학습 실패: {response.status_code}")
            print(f"   응답: {response.text}")
            return
    except Exception as e:
        print(f"❌ 스타일 학습 중 오류: {e}")
        return
    
    time.sleep(1)
    
    # Step 3: 이미지 생성 테스트
    print_step(3, "이미지 생성 테스트")
    for i, prompt in enumerate(USER_PROMPTS, 1):
        print(f"\n--- 이미지 생성 {i}/{len(USER_PROMPTS)} ---")
        print(f"프롬프트: {prompt}")
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{BASE_URL}/api/v1/generate-image",
                json={
                    "story_id": STORY_ID,
                    "node_id": f"{NODE_ID}-{i}",
                    "user_prompt": prompt,
                    "node_text": f"노드 {i}의 내용"
                },
                timeout=120
            )
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ 이미지 생성 성공! (소요 시간: {elapsed:.2f}초)")
                print(f"   이미지 URL: {BASE_URL}{data.get('image_url', '')}")
                print(f"   개선된 프롬프트: {data.get('enhanced_prompt', '')[:100]}...")
                
                # 이미지 파일 확인
                image_url = f"{BASE_URL}{data.get('image_url', '')}"
                img_response = requests.get(image_url, timeout=10)
                if img_response.status_code == 200:
                    print(f"   ✅ 이미지 파일 확인 완료 ({len(img_response.content)} bytes)")
                else:
                    print(f"   ⚠️ 이미지 파일 접근 실패")
            else:
                print(f"❌ 이미지 생성 실패: {response.status_code}")
                print(f"   응답: {response.text}")
        except Exception as e:
            print(f"❌ 이미지 생성 중 오류: {e}")
        
        time.sleep(1)
    
    print("\n" + "="*60)
    print("테스트 완료!")
    print("="*60)
    print(f"\n생성된 이미지 확인:")
    for i in range(1, len(USER_PROMPTS) + 1):
        print(f"  {BASE_URL}/api/v1/images/{STORY_ID}/{NODE_ID}-{i}")

def test_sensitive_prompts():
    """민감한 프롬프트로 프롬프트 정제 기능 테스트"""
    print("\n" + "="*60)
    print("민감한 프롬프트 정제 기능 테스트")
    print("="*60)

    # Step 1: 서버 헬스 체크
    print_step(1, "서버 헬스 체크")
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print("✅ 서버 연결 성공")
        else:
            print(f"❌ 서버 응답 오류: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ 서버 연결 실패: {e}")
        print("   서버를 먼저 실행하세요: python main.py")
        return

    # Step 2: 스타일 학습 (이미 학습된 경우 스킵)
    print_step(2, "소설 스타일 학습 (이미 학습된 경우 스킵)")

    # Step 3: 민감한 프롬프트로 이미지 생성 테스트
    print_step(3, "민감한 프롬프트로 이미지 생성 테스트")
    for i, prompt in enumerate(SENSITIVE_PROMPTS, 1):
        print(f"\n--- 이미지 생성 {i}/{len(SENSITIVE_PROMPTS)} ---")
        print(f"프롬프트: {prompt}")
        print("⚠️ 이 프롬프트는 안전 필터에 의해 차단될 수 있습니다.")
        print("   서버는 단일 시도 후 차단되면 422로 응답하며, 사용자 업로드를 유도합니다.")

        try:
            start_time = time.time()
            response = requests.post(
                f"{BASE_URL}/api/v1/generate-image",
                json={
                    "story_id": STORY_ID,
                    "node_id": f"sensitive-{i}",
                    "user_prompt": prompt,
                    "node_text": f"민감한 프롬프트 테스트 {i}"
                },
                timeout=120
            )
            elapsed = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                print(f"✅ 이미지 생성 성공! (소요 시간: {elapsed:.2f}초)")
                print(f"   이미지 URL: {BASE_URL}{data.get('image_url', '')}")
                print(f"   개선된 프롬프트: {data.get('enhanced_prompt', '')[:150]}...")
            else:
                print(f"❌ 이미지 생성 실패: {response.status_code}")
                print(f"   응답: {response.text}")
        except Exception as e:
            print(f"❌ 이미지 생성 중 오류: {e}")

        time.sleep(2)

    print("\n" + "="*60)
    print("민감한 프롬프트 테스트 완료!")
    print("="*60)

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--sensitive":
        # 민감한 프롬프트 테스트
        test_sensitive_prompts()
    else:
        # 일반 테스트
        test_image_generation()

        print("\n" + "="*60)
        print("💡 Tip: 민감한 프롬프트 테스트를 실행하려면:")
        print("   python test_image_gen.py --sensitive")
        print("="*60)







