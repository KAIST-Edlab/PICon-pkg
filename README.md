# PICON — Persona Interview & CONsistency Evaluation

PICON is a framework that automatically interviews and evaluates LLM-based personas across three dimensions: **Consistency**, **External Verifiability**, and **Stability**.

Provide your own persona (system prompt), and PICON will interrogate it from multiple angles, analyze the responses, and produce quantitative scores.

---

## Project Structure

```
interrogation_eval/
│
├── main.py                                  # CLI entry point — run interviews from the terminal
├── pyproject.toml                           # Package build config & dependency list
├── README.md
│
├── picon/                                   # Core package (pip install -e . 으로 설치)
│   ├── __init__.py                         # Public API — run(), interview(), evaluate() 노출
│   ├── api.py                              # 위 세 함수의 실제 구현체. PiconResult 클래스 정의
│   ├── config.py                           # 기본 설정값(모델명, 턴 수 등) & 프롬프트 파일 경로 헬퍼
│   ├── schemas.py                          # Pydantic 데이터 모델 — Turn, Action, State 등 인터뷰 상태 표현
│   ├── utils.py                            # 공용 유틸리티 — LLM API 호출(litellm), JSON 읽기/쓰기
│   │
│   ├── agents/                             # 인터뷰에 참여하는 AI 에이전트들
│   │   ├── __init__.py                    # get_agent(), BaseAgent 공개
│   │   ├── base_agent.py                  # 모든 에이전트의 추상 베이스 클래스 (role, memory, act())
│   │   ├── agent_factory.py               # 에이전트 팩토리 — 문자열 타입명으로 에이전트 객체 생성
│   │   ├── questioner_agent.py            # 질문 생성 에이전트 — 인터뷰 질문을 동적으로 생성
│   │   ├── extractor_agent.py             # 엔티티 추출 에이전트 — 답변에서 인물/장소/사실 추출
│   │   ├── claim_agent.py                 # 주장 추출 에이전트 — 답변에서 검증 가능한 주장(claim) 추출
│   │   ├── evaluator.py                   # 평가 에이전트 — 반복 질문 답변 간 일관성/모순 판정
│   │   ├── web_search_agent.py            # 웹 검색 에이전트 — 추출된 주장의 사실 여부를 검색으로 확인
│   │   ├── kg_agent.py                    # 지식 그래프 에이전트 — (주어, 술어, 목적어) 트리플렛 추출
│   │   └── prompts/                       # 각 에이전트의 시스템 프롬프트 (.txt)
│   │       ├── questioner.txt             #   질문 생성 지시문
│   │       ├── entity_extractor.txt       #   엔티티 추출 지시문
│   │       ├── claim_extractor_prompt.txt #   주장 추출 지시문
│   │       ├── evaluator_prompt.txt       #   일관성 평가 지시문
│   │       ├── websearch_prompt.txt       #   웹 검색 필요성 판단 지시문
│   │       ├── nhd_detector.txt           #   AI/Human 판별 지시문
│   │       ├── conflict_detection.txt     #   논리적 모순 탐지 지시문
│   │       ├── abstain.txt                #   답변 회피 탐지 지시문
│   │       └── kg_agent_prompt.txt        #   지식 그래프 추출 지시문
│   │
│   ├── env/                               # 인터뷰 환경 — 전체 인터뷰 흐름을 관리
│   │   ├── __init__.py                   # InterrogationEnv 공개
│   │   ├── interrogation_env.py          # 핵심 오케스트레이터 — 에이전트들을 조율하며 턴별 인터뷰 진행
│   │   │                                 #   흐름: 기본질문 → 본 심문 → 반복질문 → 평가
│   │   ├── interviewee_simulator.py      # (레거시) 통합 인터뷰이 시뮬레이터
│   │   ├── wvs_orthogonal_questions.json # 사전 정의 질문 은행 (WVS 데이터셋 기반)
│   │   ├── interrogation_instruct.txt    # 인터뷰 진행 지시문
│   │   │
│   │   ├── interviewee_simulator/        # 인터뷰이(피평가 대상) 시뮬레이터
│   │   │   ├── __init__.py
│   │   │   ├── base_interviewee_simulator.py   # 추상 베이스 — 응답 재시도, AI 탐지 등
│   │   │   ├── generic_agent_simulator.py      # 범용 시뮬레이터 — OpenAI 호환 API면 무엇이든 연결
│   │   │   ├── simulator_factory.py            # 시뮬레이터 팩토리 — baseline 이름으로 생성
│   │   │   └── persona_prompt_builders.py      # 페르소나 프롬프트 빌더 — 다양한 포맷의 페르소나 데이터를 시스템 프롬프트로 변환
│   │   │
│   │   ├── personas/                     # 페르소나 데이터 & 베이스라인
│   │   │   ├── human_simulacra/          #   HumanSimulacra 베이스라인 — LangChain 기반 캐릭터 시뮬레이션
│   │   │   │   ├── hs_agents.py          #     HumanSimulacra 에이전트 래퍼
│   │   │   │   ├── prompts/              #     전용 프롬프트
│   │   │   │   └── Characters/           #     캐릭터 프로필 (속성, 기억, Q&A, 스토리)
│   │   │   └── persona_hub/              #   PersonaHub 베이스라인 — HuggingFace 데이터셋에서 페르소나 생성
│   │   │       └── named_persona.py      #     LLM으로 페르소나에 이름 부여
│   │   │
│   │   └── test_env/                     # 개별 에이전트 테스트 환경 (개발/디버깅용)
│   │       ├── questioner_test_env.py    #   질문 에이전트 단독 테스트
│   │       ├── evaluator_test_env.py     #   평가 에이전트 단독 테스트
│   │       ├── conflict_test_env.py      #   모순 탐지 테스트
│   │       ├── entity_extractor_test_env.py  # 엔티티 추출 테스트
│   │       ├── kg_agent_test_env.py      #   지식 그래프 테스트
│   │       └── web_search_test_env.py    #   웹 검색 테스트
│   │
│   └── tools/                            # 외부 API 연동 도구
│       ├── __init__.py                  # SerperSearch, GoogleGeocodeValidate 공개
│       ├── web_search.py                # 웹 검색 — Serper, Tavily, Google Custom Search 지원
│       │                                #   웹페이지 파싱 + BM25 관련성 랭킹 포함
│       └── address_locator.py           # 주소 검증 — Google Geocoding API로 실제 주소 확인
│
├── servers/                              # 외부 서비스 래핑 서버 (OpenAI 호환 API로 변환)
│   ├── characterai_server.py            # CharacterAI → /v1/chat/completions 래퍼
│   ├── human_simulacra_server.py        # HumanSimulacra → /v1/chat/completions 래퍼
│   └── consistent_llm_server.py         # Consistent LLM → /v1/chat/completions 래퍼
│
├── analysis/                             # 결과 분석 & 시각화
│   ├── evaluate_result.py               # 평가 결과 후처리 — 모순 탐지 프롬프트 & 판정 로직
│   ├── abstain_analysis.py              # 답변 회피 분류기 — "모르겠다" 등 회피 응답 탐지
│   └── visualize.py                     # Streamlit 대시보드 — Plotly 차트, 통계 검정 (Mann-Whitney U 등)
│
├── web_interview/                        # 사람 인터뷰 수집용 웹 UI
│   ├── frontend/                        # Next.js + React + Tailwind 프론트엔드
│   ├── api/                             # FastAPI 백엔드
│   └── vercel.json                      # Vercel 배포 설정
│
└── scripts/                              # 실행 스크립트 모음
```

### How It Works — Interview Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     Interview Pipeline                          │
│                                                                 │
│  1. Get-to-Know Phase     사전 정의된 기본 질문 (WVS)            │
│         ↓                                                       │
│  2. Main Interrogation    AI가 동적으로 질문 생성 & 심문          │
│         │                                                       │
│         ├── Questioner     → 다음 질문 생성                      │
│         ├── Interviewee    → 페르소나가 답변                      │
│         ├── Extractor      → 답변에서 주장/엔티티 추출            │
│         ├── Web Search     → 추출된 주장을 웹에서 사실 확인       │
│         └── Evaluator      → 이전 답변과의 일관성 판정            │
│         ↓                                                       │
│  3. Repeat Phase          기본 질문을 재질문 → 일관성 비교        │
│         ↓                                                       │
│  4. Finalize              점수 계산 & 결과 저장                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Installation

```bash
# Basic install
pip install -e .

# Full install (CharacterAI, Google GenAI, etc.)
pip install -e ".[all]"
```

## Environment Variables

Copy `.env.example` to `.env` and fill in your API keys.

```bash
cp .env.example .env
```

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Gemini model calls (default interviewer/evaluator) |
| `GOOGLE_API_KEY` | Google API (same value as `GEMINI_API_KEY`) |
| `OPENAI_API_KEY` | OpenAI model calls |
| `ANTHROPIC_API_KEY` | Anthropic model calls |
| `SERPER_API_KEY` | Web search for external verification |
| `GOOGLE_GEOCODE` | Address validation (Google Geocoding API) |
| `GOOGLE_CLAIM_SEARCH` | Fact-check search (Google Custom Search API) |
| `GOOGLE_CX_ID` | Custom Search Engine ID |

---

## Quick Start (Python API)

```python
import picon

result = picon.run(
    persona="You are a 35-year-old software engineer named John...",
    name="John",
    model="gemini/gemini-3-flash",   # LLM for the persona
    num_turns=20,
    num_sessions=2,
    do_eval=True,
)

# Check results
print(result.success)       # True / False
print(result.eval_scores)   # Evaluation scores dict
print(result.summary)       # Summary statistics

# Save
result.save("results/john.json")
```

### Interview Only (no evaluation)

```python
result = picon.interview(
    persona="persona.txt",   # File path is also supported
    name="Jane",
    model="gemini/gemini-3-flash",
)
```

### Evaluate Existing Results

```python
scores = picon.evaluate("results/john.json")
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

## Self-Hosted Model Evaluation

For OpenAI-compatible endpoints (vLLM, etc.), specify `api_base`.

```python
result = picon.run(
    persona="",                                    # Empty if the server manages the persona
    name="Llama3",
    model="meta-llama/Llama-3-8B",
    api_base="http://localhost:8000/v1",
    num_turns=30,
)
```

---

## CLI Usage

```bash
# Basic run
python main.py \
    --agent_model gemini/gemini-2.5-flash \
    --agent_persona persona.txt \
    --agent_name "John" \
    --num_turns 20 \
    --num_sessions 2 \
    --do_eval

# Self-hosted model
python main.py \
    --agent_api_base http://localhost:8000/v1 \
    --agent_model meta-llama/Llama-3-8B \
    --agent_persona "You are a 30-year-old teacher..." \
    --agent_name "Teacher"

# Wrapping server (CharacterAI, etc.)
python main.py \
    --agent_api_base http://localhost:8001/v1 \
    --agent_model characterai \
    --agent_name "Mary Jones"
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--agent_model` | Model for the persona | (required) |
| `--agent_persona` | System prompt (string or .txt path) | `None` |
| `--agent_name` | Interviewee name | `Agent` |
| `--agent_api_base` | OpenAI-compatible API URL | `None` (litellm routing) |
| `--num_turns` | Number of interview turns | `30` |
| `--num_sessions` | Number of repeated sessions | `2` |
| `--do_eval` | Run evaluation | `False` |
| `--eval_factors` | Select evaluation factors | `None` (all) |
| `--questioner_model` | Questioner agent model | `gemini/gemini-2.5-flash` |
| `--evaluator_model` | Evaluator agent model | `gemini/gemini-2.5-flash` |
| `--output_dir` | Output directory | `data/results` |

---

## Advanced: Using Components Directly

Import internal components to build custom pipelines.

```python
from picon.agents import get_agent
from picon.env import InterrogationEnv
from picon.tools import SerperSearch, GoogleGeocodeValidate
from picon.config import get_prompt_path

# Build agents manually
agents = {
    "questioner": get_agent("questioner", "my_custom_questioner.txt", model="gpt-5"),
    "extractor": get_agent("claim_extractor", get_prompt_path("claim_extractor_prompt.txt"), model="gpt-5.1"),
    "web_search": get_agent("web_search", get_prompt_path("websearch_prompt.txt"), model="gpt-5"),
    "evaluator": get_agent("evaluator", get_prompt_path("evaluator_prompt.txt"), model="gemini/gemini-2.5-flash"),
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

## Evaluation Metrics

| Metric | Description |
|--------|-------------|
| **Internal Responsiveness** | Relevance of answers to questions |
| **Internal Consistency** | Consistency of answers to repeated questions |
| **Internal Harmonic Mean** | Harmonic mean of Responsiveness and Consistency |
| **External Wilson Score** | Proportion of verifiable claims confirmed by web search (Wilson CI) |
| **Inter-session Stability** | Answer stability across sessions |
| **Intra-session Stability** | Answer stability within a session |

---

## License

TBD
