# Simulator 통합 전략: 모든 시뮬레이터 → GenericAgentSimulator

## 핵심 아이디어

**모든 평가 대상을 OpenAI-compatible API endpoint로 통일한다.**

커스텀 로직(CharacterAI WebSocket, HumanSimulacra 에이전트 등)은 각자의 **API 서버 뒤에** 숨긴다.
평가 시스템 입장에서는 전부 동일한 `/v1/chat/completions` endpoint.

```
┌─────────────────────┐
│  InterrogationEnv   │
│  (평가 시스템)        │
└────────┬────────────┘
         │  OpenAI-compatible API call
         ▼
┌─────────────────────┐
│ GenericAgentSimulator│  ← 유일한 시뮬레이터 클래스
│  api_base + model    │
└────────┬────────────┘
         │
    ┌────┴────┬──────────┬──────────┬────────────┐
    ▼         ▼          ▼          ▼            ▼
  vLLM     OpenAI    CharacterAI  HumanSimulacra  ...
 (직접)    (직접)    (래핑 서버)   (래핑 서버)    (어떤 서버든)
```

---

## 현황: 9개 시뮬레이터

### A. 직접 대체 (5개) — 이미 OpenAI-compatible chat completion 패턴

| 시뮬레이터 | 시스템 프롬프트 | 유저 메시지 래핑 | 특이사항 |
|---|---|---|---|
| **PersonaHub** | `"You are {persona}..."` | 없음 | litellm 직접 호출 |
| **Twin2K500** | survey instruction + persona | 없음 | host:port 옵션 |
| **DeepPersona** | 2-msg init (system + user) | `"user request: {msg}"` | → 1개 system으로 합침 |
| **LLMGenerated** | 구조화 데이터 → 프롬프트 생성 | `"### QUESTION ###\n{msg}..."` | temperature=0.8, top_p=0.9 |
| **OpenCharacter** | persona + profile 템플릿 | 없음 | max_tokens=1024, temperature=0.9 |

→ `main.py`에서 시스템 프롬프트를 포매팅한 뒤 `GenericAgentSimulator`에 전달하면 끝.

### B. 래핑 서버 필요 (3개) — 자체 프로토콜/로직을 API 서버로 감쌈

| 시뮬레이터 | 내부 로직 | 래핑 서버가 할 일 |
|---|---|---|
| **CharacterAI** | PyCharacterAI async WebSocket | WebSocket 호출 → `/v1/chat/completions` 응답으로 변환 |
| **HumanSimulacra** | `Top_agent` (캐릭터 파일, Memories, Attributes 로드) | 에이전트 로직 실행 → chat completion 응답 반환 |
| **ConsistentLLM** | 플레인 텍스트 히스토리 조립 + instruction 주입 | 커스텀 히스토리 관리 → vLLM 호출 → 응답 반환 |

### C. 삭제

- **NaiveHumanSimulacra**: 삭제 예정

---

## 구현 계획

### Step 1: GenericAgentSimulator 확장

`generic_agent_simulator.py`를 모든 케이스를 커버하도록 확장:

```python
# 필수
persona: str              # 시스템 프롬프트
model: str                # 모델 이름

# 옵션
api_base: str = None      # API endpoint URL. None이면 litellm 기본 라우팅
api_key: str = "no-key"   # API 키
name: str = "GenericAgent" # 인터뷰이 이름
user_message_template: str = "{message}"   # 유저 메시지 래핑
completion_kwargs: dict = {}               # temperature, top_p 등 추가 파라미터
```

변경 사항:
- `api_base`를 required → optional로 변경
- `host`/`port`가 주어지면 `api_base = f"http://{host}:{port}/v1"` 자동 구성
- `user_message_template` 추가 (DeepPersona, LLMGenerated 대응)
- `completion_kwargs` 추가 (OpenCharacter, LLMGenerated 대응)
- DeepPersona의 2-msg init → 1개 system 메시지로 합침 (truncation 안전)

### Step 2: 래핑 서버 구현 (B그룹 3개)

각 서버는 `/v1/chat/completions` endpoint를 노출하는 FastAPI 앱:

**공통 구조:**
```python
# servers/{name}_server.py
from fastapi import FastAPI
app = FastAPI()

@app.post("/v1/chat/completions")
def chat_completions(request):
    message = request.messages[-1]["content"]
    response = internal_logic(message)  # 각 시뮬레이터 고유 로직
    return {
        "choices": [{"message": {"role": "assistant", "content": response}}]
    }
```

**CharacterAI 서버** (`servers/characterai_server.py`):
- 초기화: `PyCharacterAI` 클라이언트 + chat session 생성
- 요청마다: `client.chat.send_message()` → 응답 반환
- 세션 관리: character_id별 클라이언트 풀

**HumanSimulacra 서버** (`servers/human_simulacra_server.py`):
- 초기화: `Top_agent(character_name, model)` 로드
- 요청마다: `top_agent.send_message()` → 응답 반환
- 캐릭터별 에이전트 인스턴스 관리

**ConsistentLLM 서버** (`servers/consistent_llm_server.py`):
- 초기화: tokenizer + persona + instruction 로드
- 요청마다: 플레인 텍스트 히스토리 조립 → vLLM 호출 → 응답 반환
- 히스토리 truncation 로직 내장

### Step 3: main.py 시스템 프롬프트 구성을 kwargs 블록으로 이동

**A그룹 (직접 대체 5개)** — 시스템 프롬프트를 main.py에서 포매팅:

```python
# PersonaHub
persona = (
    f"You are {data['persona']}\n\n"
    "Please stay in your character and comply with the persona. "
    "Don't mention that you are an AI model."
)

# Twin2K500
persona = (
    "You are an AI assistant. Your task is to answer the 'New Survey Question' as "
    "if you are the individual described in the 'Persona Profile'...\n\n"
    f"{data['persona_json']}"
)

# DeepPersona (2-msg → 1-msg 합침)
persona = (
    "Given the following user profile and request, generate a "
    "personalized response tailored to the user's background and attributes.\n\n"
    f"User profile: {data};"
)

# LLMGenerated
persona_prompt = build_llm_generated_persona_prompt(data)  # 유틸 함수
persona = f"You are an AI assistant tasked with generating realistic opinions...\n\n{persona_prompt}"

# OpenCharacter
persona = (
    "You are an AI character with the following Persona.\n\n"
    f"# Persona\n{data['persona']}\n\n"
    f"# Character Profile\n{data['character']}\n\n"
    "Please stay in your character..."
)
```

모든 kwargs에 `"baseline_name": "generic_agent"` 설정.

**B그룹 (래핑 서버 3개)** — 서버 주소만 전달:

```python
# CharacterAI
kwargs = {
    "baseline_name": "generic_agent",
    "api_base": "http://localhost:8001/v1",
    "model": "characterai",
    "persona": "",  # 서버 내부에서 관리
    "name": persona['character_name'],
}

# HumanSimulacra
kwargs = {
    "baseline_name": "generic_agent",
    "api_base": "http://localhost:8002/v1",
    "model": "human_simulacra",
    "persona": "",  # 서버 내부에서 관리
    "name": name,
}

# ConsistentLLM
kwargs = {
    "baseline_name": "generic_agent",
    "api_base": "http://localhost:8003/v1",
    "model": "consistent_llm",
    "persona": "",  # 서버 내부에서 관리
    "name": data['name'],
}
```

### Step 4: LLMGenerated 프롬프트 빌더 추출

`LLMGeneratedSimulator._create_comprehensive_persona_prompt()`를 독립 함수로 추출:
- 위치: `src/env/interviewee_simulator/persona_prompt_builders.py`
- `main.py`에서 import하여 kwargs 구성 시 사용

### Step 5: simulator_factory.py 단순화

```python
def get_interviewee_simulator(baseline_name: str, **kwargs):
    if baseline_name == "generic_agent":
        from ...generic_agent_simulator import GenericAgentSimulator
        return GenericAgentSimulator(**kwargs)
    else:
        raise ValueError(f"Unsupported: {baseline_name}. Use generic_agent.")
```

기존 baseline name은 하위 호환성을 위해 `generic_agent`로 리다이렉트:

```python
# 하위 호환
LEGACY_BASELINES = {"persona_hub", "twin_2k_500", "deeppersona",
                    "llm_generated", "opencharacter",
                    "characterai", "human_simulacra", "consistent_llm"}
if baseline_name in LEGACY_BASELINES:
    baseline_name = "generic_agent"
```

### Step 6: 기존 파일 정리

- **NaiveHumanSimulacra** (`naive_human_simulacra_simulator.py`): 삭제
- A그룹 5개 시뮬레이터 파일: deprecation warning 추가, 후속 PR에서 삭제
- B그룹 3개 시뮬레이터 파일: 로직을 `servers/`로 이동 후, 후속 PR에서 삭제

### Step 7: CLI 인터페이스 통일

`main.py` argparse를 정리하여 `generic_agent` 중심으로:

```bash
# A그룹: 기존 baseline name 그대로 사용 (내부적으로 generic_agent 변환)
python main.py --baseline_name persona_hub --simulator_model gemini/gemini-2.5-flash

# B그룹: 래핑 서버를 먼저 띄운 후
python servers/characterai_server.py --port 8001
python main.py --baseline_name characterai --agent_api_base http://localhost:8001/v1

# 완전 커스텀: 어떤 에이전트든
python main.py --baseline_name generic_agent \
  --agent_api_base http://my-agent:8000/v1 \
  --agent_model my-model \
  --agent_persona "You are ..." \
  --num_turns 50
```

---

## 파일 변경 목록

| 파일 | 변경 |
|---|---|
| `generic_agent_simulator.py` | `api_base` optional, `user_message_template`, `completion_kwargs` 추가 |
| `main.py` | 모든 baseline kwargs → `generic_agent` 변환, 프롬프트 포매팅 이동 |
| `simulator_factory.py` | 모든 baseline → `GenericAgentSimulator` 라우팅, 단순화 |
| `persona_prompt_builders.py` | **신규** — LLMGenerated 프롬프트 빌더 추출 |
| `servers/characterai_server.py` | **신규** — CharacterAI 래핑 서버 |
| `servers/human_simulacra_server.py` | **신규** — HumanSimulacra 래핑 서버 |
| `servers/consistent_llm_server.py` | **신규** — ConsistentLLM 래핑 서버 |
| `naive_human_simulacra_simulator.py` | 삭제 |
| 기존 8개 시뮬레이터 파일 | deprecation warning → 후속 PR에서 삭제 |

---

## 통합 CLI 인터페이스

모든 평가 대상을 동일한 4개 파라미터로 호출:

```bash
python main.py \
  --agent_api_base <endpoint>  \  # API endpoint (없으면 litellm 자동 라우팅)
  --agent_model <model>        \  # 모델 이름 (필수)
  --agent_persona <prompt>     \  # 시스템 프롬프트 (문자열 또는 .txt 파일 경로)
  --agent_name <name>          \  # 인터뷰이 이름
  --num_turns 50
```

### 사용 예시

#### CharacterAI (B그룹 — 래핑 서버)
```bash
# 터미널 1: 래핑 서버 실행
python servers/characterai_server.py --port 8001 --character_id <char_id> --user_id <user_id>

# 터미널 2: 인터뷰 실행
python main.py \
  --agent_api_base http://localhost:8001/v1 \
  --agent_model characterai \
  --agent_name "Raiden Shogun"
```

#### HumanSimulacra (B그룹 — 래핑 서버)
```bash
# 터미널 1: 래핑 서버 실행
python servers/human_simulacra_server.py --port 8002 --character_name "Mary Jones" --model gemini/gemini-2.5-flash

# 터미널 2: 인터뷰 실행
python main.py \
  --agent_api_base http://localhost:8002/v1 \
  --agent_model human_simulacra \
  --agent_name "Mary Jones"
```

#### OpenCharacter (A그룹 — vLLM 직접 호출)
```bash
# vLLM 서버가 localhost:8000에 실행 중이라고 가정
python main.py \
  --agent_api_base http://localhost:8000/v1 \
  --agent_model hosted_vllm/willystumblr/opencharacter-sft \
  --agent_persona "You are an AI character with the following Persona.

# Persona
A cheerful barista who loves latte art.

# Character Profile
Name: Mika
Age: 26
Occupation: Barista

Please stay in your character and comply with the Persona and Character Profile while being helpful and harmless." \
  --agent_name "Mika"
```

#### DeepPersona (A그룹 — 클라우드 API)
```bash
python main.py \
  --agent_model gemini/gemini-2.5-flash \
  --agent_persona "Given the following user profile and request, generate a personalized response tailored to the user's background and attributes.

User profile: {\"name\": \"Alex Kim\", \"age\": 32, \"occupation\": \"nurse\", \"city\": \"Portland\"};" \
  --agent_name "Alex Kim"

# 또는 페르소나 파일로
python main.py \
  --agent_model gemini/gemini-2.5-flash \
  --agent_persona deeppersona_alex.txt \
  --agent_name "Alex Kim"
```


# 폴더정리
interrogation_eval/
├── main.py                           # 배치 CLI (평가)
├── servers/                          # 래핑 서버 (CharacterAI, HumanSimulacra 등)
├── src/                              # 핵심 평가 로직
│   ├── agents/                       #   에이전트 (questioner, evaluator 등)
│   ├── tools/                        #   도구 (web_search, geocode)
│   ├── env/                          #   환경 (interrogation_env, simulators, personas)
│   ├── schemas.py
│   └── utils.py
│
└── web_interview/                              # 인터뷰 서버 (Vercel + Railway)
    ├── api/index.py                  #   FastAPI 백엔드
    ├── api/requirements.txt
    ├── frontend/                     #   Next.js 프론트엔드
    ├── web_interrogation_env.py      #   웹 전용 환경 (상태 머신)
    ├── railway.json                  #   Railway 배포 설정
    ├── .vercelignore
    └── README.md
