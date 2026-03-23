# PICON — Persona Interview & CONsistency Evaluation

PICON은 LLM 기반 페르소나의 **일관성(Consistency)**, **외부 검증 가능성(External Verifiability)**, **안정성(Stability)**을 자동으로 인터뷰하고 평가하는 프레임워크입니다.

자신이 만든 페르소나(시스템 프롬프트)를 넣으면, PICON이 다각도로 질문하고 답변을 분석하여 정량적 점수를 산출합니다.

---

## 설치

```bash
# 기본 설치
pip install -e .

# 전체 (CharacterAI, Google GenAI 등 포함)
pip install -e ".[all]"
```

## 환경 변수

`.env.example`을 `.env`로 복사하고 API 키를 입력하세요.

```bash
cp .env.example .env
```

| 변수 | 용도 |
|------|------|
| `GEMINI_API_KEY` | Gemini 모델 호출 (기본 인터뷰어/평가자) |
| `GOOGLE_API_KEY` | Google API (GEMINI_API_KEY와 동일 값) |
| `OPENAI_API_KEY` | OpenAI 모델 호출 |
| `ANTHROPIC_API_KEY` | Anthropic 모델 호출 |
| `SERPER_API_KEY` | 웹 검색 (외부 검증) |
| `GOOGLE_GEOCODE` | 주소 검증 (Google Geocoding API) |
| `GOOGLE_CLAIM_SEARCH` | 팩트체크 검색 (Google Custom Search API) |
| `GOOGLE_CX_ID` | Custom Search Engine ID |

---

## 빠른 시작 (Python API)

```python
import picon

result = picon.run(
    persona="""
    당신은 서울 강남에 사는 35세 소프트웨어 엔지니어 박민수입니다.
    카카오에서 백엔드 개발을 하고 있으며, 취미는 등산과 커피 로스팅입니다.
    """,
    name="박민수",
    model="gemini/gemini-2.5-flash",   # 페르소나가 사용할 LLM
    num_turns=20,
    num_sessions=2,
    do_eval=True,
)

# 결과 확인
print(result.success)       # True / False
print(result.eval_scores)   # 평가 점수 dict
print(result.summary)       # 요약 통계

# 저장
result.save("results/minsu.json")
```

### 인터뷰만 (평가 없이)

```python
result = picon.interview(
    persona="persona.txt",   # 파일 경로도 가능
    name="홍길동",
    model="gpt-4o",
)
```

### 기존 결과에 대해 평가만

```python
scores = picon.evaluate("results/minsu.json")
print(scores)
# {
#   "internal_harmonic_mean": 0.85,
#   "internal_responsiveness": 0.90,
#   "internal_consistency": 0.81,
#   "external_wilson": 0.72,
#   "inter_session_stability": 0.88,
#   "intra_session_stability": 0.91,
# }
```

---

## 자체 호스팅 모델 평가

vLLM 등 OpenAI-compatible 엔드포인트가 있으면 `api_base`를 지정합니다.

```python
result = picon.run(
    persona="",                                    # 서버가 페르소나 관리 시 빈 문자열
    name="Llama3",
    model="meta-llama/Llama-3-8B",
    api_base="http://localhost:8000/v1",
    num_turns=30,
)
```

---

## CLI 사용법

```bash
# 기본 실행
python main.py \
    --agent_model gemini/gemini-2.5-flash \
    --agent_persona persona.txt \
    --agent_name "박민수" \
    --num_turns 20 \
    --num_sessions 2 \
    --do_eval

# 자체 호스팅 모델
python main.py \
    --agent_api_base http://localhost:8000/v1 \
    --agent_model meta-llama/Llama-3-8B \
    --agent_persona "You are a 30-year-old teacher..." \
    --agent_name "Teacher"

# 래핑 서버 (CharacterAI 등)
python main.py \
    --agent_api_base http://localhost:8001/v1 \
    --agent_model characterai \
    --agent_name "Mary Jones"
```

### 주요 CLI 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--agent_model` | 페르소나가 사용할 모델 | (필수) |
| `--agent_persona` | 시스템 프롬프트 (문자열 또는 .txt 경로) | `None` |
| `--agent_name` | 인터뷰이 이름 | `Agent` |
| `--agent_api_base` | OpenAI-compatible API URL | `None` (litellm 라우팅) |
| `--num_turns` | 인터뷰 턴 수 | `30` |
| `--num_sessions` | 세션 반복 횟수 | `2` |
| `--do_eval` | 평가 실행 여부 | `False` |
| `--eval_factors` | 평가 항목 선택 | `None` (전체) |
| `--questioner_model` | 질문자 에이전트 모델 | `gemini/gemini-2.5-flash` |
| `--evaluator_model` | 평가자 에이전트 모델 | `gemini/gemini-2.5-flash` |
| `--output_dir` | 결과 저장 디렉토리 | `data/results` |

---

## 고급: 컴포넌트 직접 사용

내부 컴포넌트를 개별적으로 import하여 커스텀 파이프라인을 구성할 수 있습니다.

```python
from picon.agents import get_agent
from picon.env import InterrogationEnv
from picon.tools import SerperSearch, GoogleGeocodeValidate
from picon.config import get_prompt_path

# 에이전트 직접 구성
agents = {
    "questioner": get_agent("questioner", "my_custom_questioner.txt", model="gpt-4o"),
    "extractor": get_agent("claim_extractor", get_prompt_path("claim_extractor_prompt.txt")),
    "web_search": get_agent("web_search", get_prompt_path("websearch_prompt.txt")),
    "evaluator": get_agent("evaluator", get_prompt_path("evaluator_prompt.txt")),
}

tools = {
    "serper_search": SerperSearch(api_key="your-key"),
}

env = InterrogationEnv(
    agents=agents,
    tools=tools,
    max_turns=20,
    baseline_name="generic_agent",
    model="gemini/gemini-3-flash",
    persona="You are ...",
    name="CustomAgent",
)

env.reset()
done = False
while not done:
    state, done = env.step()
env.finalize()
```

---

## 평가 지표

| 지표 | 설명 |
|------|------|
| **Internal Responsiveness** | 질문에 대한 답변의 관련성 |
| **Internal Consistency** | 반복 질문에 대한 답변 일관성 |
| **Internal Harmonic Mean** | Responsiveness와 Consistency의 조화평균 |
| **External Wilson Score** | 웹 검색으로 검증 가능한 주장의 비율 (Wilson CI) |
| **Inter-session Stability** | 세션 간 답변 안정성 |
| **Intra-session Stability** | 세션 내 답변 안정성 |

---

## 프로젝트 구조

```
picon/                      # 패키지 루트
├── __init__.py             # 공개 API: run(), interview(), evaluate()
├── api.py                  # 고수준 함수 구현
├── config.py               # 기본 설정 & 리소스 경로 헬퍼
├── schemas.py              # Pydantic 데이터 모델
├── utils.py                # 유틸리티 (LLM 호출, 파일 I/O)
├── agents/                 # 인터뷰/평가 에이전트
│   ├── agent_factory.py    # 에이전트 생성 팩토리
│   ├── questioner_agent.py # 질문 생성
│   ├── extractor_agent.py  # 엔티티/클레임 추출
│   ├── evaluator.py        # 일관성/검증 평가
│   ├── web_search_agent.py # 웹 검색 판단
│   └── prompts/            # 시스템 프롬프트 (.txt)
├── env/                    # 인터뷰 환경
│   ├── interrogation_env.py
│   └── interviewee_simulator/
│       ├── generic_agent_simulator.py
│       └── simulator_factory.py
└── tools/                  # 외부 도구
    ├── web_search.py       # Serper, Tavily, Google 검색
    └── address_locator.py  # Google Geocode 검증

main.py                     # CLI 엔트리포인트
servers/                    # 래핑 서버 (CharacterAI, HumanSimulacra 등)
web_interview/              # 웹 기반 인터뷰 UI
analysis/                   # 결과 분석 & 시각화
scripts/                    # 실행 스크립트
```

---

## 라이선스

TBD
