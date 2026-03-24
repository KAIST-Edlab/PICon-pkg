# PICON — Persona Interrogation framework for Consistency evaluation

PICON is a framework that automatically interviews and evaluates LLM-based personas across three dimensions: **Consistency**, **External Verifiability**, and **Stability**.

Provide your own persona (system prompt), and PICON will interrogate it from multiple angles, analyze the responses, and produce quantitative scores.

---

## Project Structure

```
picon/                       # Core package
├── __init__.py              #   Public API: run(), interview(), evaluate(), run_interview(), run_evaluation()
├── api.py                   #   Implements the public API functions above; defines PiconResult
├── config.py                #   Default settings (model names, turn counts) & prompt path helpers
├── schemas.py               #   Pydantic models for interview state (Turn, Action, State, etc.)
├── utils.py                 #   Shared helpers — LLM calls via litellm, JSON I/O
│
├── agents/                  #   AI agents that participate in the interview
│   ├── agent_factory.py     #     Creates agent objects by type name (e.g. "questioner")
│   ├── questioner_agent.py  #     Dynamically generates follow-up interview questions
│   ├── extractor_agent.py   #     Extracts entities (people, places, facts) from answers
│   ├── claim_agent.py       #     Extracts verifiable claims from answers
│   ├── evaluator.py         #     Judges consistency/contradiction between repeated answers
│   ├── web_search_agent.py  #     Decides whether to web-search a claim, then verifies it
│   ├── kg_agent.py          #     Builds knowledge-graph triplets (subject, predicate, object)
│   └── prompts/             #     System prompt files (.txt) for each agent
│
├── env/                     #   Interview environment — orchestrates the full interview flow
│   ├── interrogation_env.py #     Core orchestrator: coordinates agents across turns
│   ├── interviewee_simulator/
│   │   ├── generic_agent_simulator.py  # Connects to any OpenAI-compatible LLM endpoint
│   │   ├── simulator_factory.py        # Factory: creates the right simulator by baseline name
│   │   └── persona_prompt_builders.py  # Converts various persona formats into system prompts
│   ├── personas/            #     Bundled persona baselines (HumanSimulacra, PersonaHub)
│   └── test_env/            #     Standalone test harnesses for individual agents
│
└── tools/                   #   External API integrations
    ├── web_search.py        #     Web search (Serper, Tavily, Google) + page parsing & BM25 ranking
    └── address_locator.py   #     Address validation via Google Geocoding API

main.py                      # CLI entry point (thin wrapper around picon.api)
servers/                     # Wrapping servers — expose CharacterAI, HumanSimulacra, etc. as OpenAI-compatible APIs
web_interview/               # Web UI for collecting human interviews (Next.js frontend + FastAPI backend)
scripts/                     # Batch run scripts
```

### How It Works — Interview Pipeline

```
1. Get-to-Know        Ask predefined demographic questions (WVS dataset)
       |
2. Main Interrogation Each turn runs this agent chain:
       |
       |-- Questioner    Generate the next question based on conversation history
       |-- Interviewee   The persona under evaluation answers the question
       |-- Extractor     Pull out entities and verifiable claims from the answer
       |-- Web Search    Fact-check extracted claims against the web
       '-- Evaluator     Compare this answer with previous answers for consistency
       |
3. Repeat Phase        Re-ask the get-to-know questions to measure stability
       |
4. Finalize            Compute all evaluation scores and save results
```

---

## Installation

### Option A — Clone the repo (development / full access)

```bash
git clone https://github.com/willystumblr/picon.git
cd picon
pip install -e .        # basic
pip install -e ".[all]" # full (CharacterAI, Google GenAI, etc.)
```

### Option B — Install as a package (no repo needed)

```bash
pip install git+https://github.com/willystumblr/picon.git
# full extras:
pip install "picon[all] @ git+https://github.com/willystumblr/picon.git"
```

## Environment Variables

**Option A:** copy the template and fill in your keys.

```bash
cp .env.example .env
```

**Option B:** create a `.env` file manually (or export variables in your shell).

```bash
# .env
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
```

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Gemini model calls |
| `GOOGLE_API_KEY` | Google API (same value as `GEMINI_API_KEY`) |
| `OPENAI_API_KEY` | OpenAI model calls |
| `ANTHROPIC_API_KEY` | Anthropic model calls |
| `SERPER_API_KEY` | Web search for external verification |
| `GOOGLE_GEOCODE` | Address validation (Google Geocoding API) |
| `GOOGLE_CLAIM_SEARCH` | Fact-check search (Google Custom Search API) |
| `GOOGLE_CX_ID` | Custom Search Engine ID |

---

## Usage

PICON can be used as a **Python library** or via the **CLI**. Any system that exposes an OpenAI-compatible `/v1/chat/completions` endpoint can be evaluated.

---

### Python API (recommended)

#### One-shot: interview + evaluation

```python
import picon

result = picon.run(
    persona="You are a 35-year-old software engineer living in Seoul...",
    name="John",
    model="gpt-5",
    num_turns=20,
    num_sessions=2,
    do_eval=True,
)
print(result.eval_scores)
result.save("results/john.json")
```

#### Separate interview and evaluation

```python
import picon

# Step 1: interview
interview_result = picon.run_interview(
    name="John",
    model="gpt-5",
    persona="You are a 35-year-old software engineer...",
    num_turns=20,
    num_sessions=2,
)

# Step 2: evaluation (optional)
persona_stats = picon.run_evaluation(interview_result, eval_factors=["internal", "external"])
print(persona_stats)
```

#### `run_interview()` parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `name` | Interviewee name | (required) |
| `model` | Model for the persona | (required) |
| `persona` | System prompt (string or `.txt` path) | `""` |
| `api_base` | OpenAI-compatible API URL | `None` (litellm routing) |
| `api_key` | API key for the persona endpoint | `None` |
| `num_turns` | Number of interview turns | `30` (from `DEFAULT_CONFIG`) |
| `num_sessions` | Number of repeated sessions | `2` (from `DEFAULT_CONFIG`) |
| `questioner_model` | Questioner agent model | `DEFAULT_CONFIG` |
| `extractor_model` | Extractor agent model | `DEFAULT_CONFIG` |
| `web_search_model` | Web search agent model | `DEFAULT_CONFIG` |
| `evaluator_model` | Evaluator agent model | `DEFAULT_CONFIG` |
| `nhd_model` | NHD detector model | `DEFAULT_CONFIG` |
| `questioner_port` | Port for self-hosted questioner | `None` |
| `extractor_port` | Port for self-hosted extractor | `None` |
| `web_search_port` | Port for self-hosted web search | `None` |
| `evaluator_port` | Port for self-hosted evaluator | `None` |
| `nhd_port` | Port for self-hosted NHD | `None` |
| `output_dir` | Output directory | `data/results` |
| `question_seed` | Random seed for question order | `42` |

Default model values are defined in `picon/config.py` → `DEFAULT_CONFIG`.

---

### CLI

Three equivalent ways to invoke the CLI:

```bash
picon ...            # after pip install (Option A or B)
python -m picon ...  # always works if picon package is installed
python main.py ...   # only when repo is cloned (Option A)
```

#### Prompt-Based (LLM-Generated / DeepPersona / Twin-2K-500)

```bash
# Cloud API
picon \
    --agent_model gpt-5 \
    --agent_persona persona.txt \
    --agent_name "John" \
    --num_turns 20 --num_sessions 2 --do_eval

# Self-hosted vLLM endpoint
picon \
    --agent_api_base http://localhost:8000/v1 \
    --agent_model meta-llama/Llama-3-8B \
    --agent_persona "You are a 30-year-old teacher named Jane..." \
    --agent_name "Jane" \
    --num_turns 20 --num_sessions 2 --do_eval
```

#### Fine-Tuned Model (OpenCharacter / ConsistentLLM)

```bash
# OpenCharacter
picon \
    --agent_api_base http://localhost:8123/v1 \
    --agent_model openai/willystumblr/opencharacter-sft-llama-3-8b-instruct \
    --agent_persona "You are a kind-hearted librarian named Alice..." \
    --agent_name "Alice" \
    --num_turns 20 --num_sessions 2 --do_eval

# ConsistentLLM — start the wrapping server first
python servers/consistent_llm_server.py \
    --port 8003 \
    --model_path /path/to/llama-8b-sft-ppo-prompt \
    --persona "You are a consistent persona..." \
    --name "John"

picon \
    --agent_api_base http://localhost:8003/v1 \
    --agent_model consistent_llm \
    --agent_name "John" \
    --num_turns 20 --num_sessions 2 --do_eval
```

#### RAG / Multi-Agent (HumanSimulacra)

```bash
# 1) Start the wrapping server
python servers/human_simulacra_server.py \
    --port 8002 \
    --character_name "Mary Jones" \
    --model gpt-5

# 2) Run the interview
picon \
    --agent_api_base http://localhost:8002/v1 \
    --agent_model human_simulacra \
    --agent_name "Mary Jones" \
    --num_turns 20 --num_sessions 2 --do_eval
```

#### Service (CharacterAI)

```bash
# 1) Start the wrapping server
python servers/characterai_server.py \
    --port 8001 \
    --character_id "ZTvEvhHRJs9KEe_NjwHoZEJFAAZ5nUV3UkTaMpNE7rY"

# 2) Run the interview
picon \
    --agent_api_base http://localhost:8001/v1 \
    --agent_model characterai \
    --agent_name "Jordan Peterson" \
    --num_turns 20 --num_sessions 2 --do_eval
```

#### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--agent_model` | Model for the persona | (required) |
| `--agent_persona` | System prompt (string or .txt path) | `None` |
| `--agent_name` | Interviewee name | `Agent` |
| `--agent_api_base` | OpenAI-compatible API URL | `None` (litellm routing) |
| `--num_turns` | Number of interview turns | `DEFAULT_CONFIG` |
| `--num_sessions` | Number of repeated sessions | `DEFAULT_CONFIG` |
| `--do_eval` | Run evaluation after interview | `False` |
| `--eval_factors` | Evaluation factors to run | `None` (all) |
| `--questioner_model` | Questioner agent model | `DEFAULT_CONFIG` |
| `--evaluator_model` | Evaluator agent model | `DEFAULT_CONFIG` |
| `--output_dir` | Output directory | `DEFAULT_CONFIG` |

---

## Advanced: Using Components Directly

```python
from picon.agents import get_agent
from picon.env import InterrogationEnv
from picon.tools import SerperSearch, GoogleGeocodeValidate
from picon.config import get_prompt_path

agents = {
    "questioner": get_agent("questioner", get_prompt_path("questioner.txt"), model="gpt-5"),
    "extractor":  get_agent("entity_extractor", get_prompt_path("entity_extractor.txt"), model="gpt-5.1"),
    "web_search": get_agent("web_search", get_prompt_path("websearch_prompt.txt"), model="gpt-5"),
    "evaluator":  get_agent("evaluator", get_prompt_path("evaluator_prompt.txt"), model="gpt-5"),
}

tools = {
    "serper_search": SerperSearch(api_key="your-key"),
    "google_geocode_validate": GoogleGeocodeValidate(api_key="your-key"),
}

env = InterrogationEnv(
    agents=agents,
    tools=tools,
    max_turns=20,
    baseline_name="generic_agent",
    model="gpt-5",
    persona="You are ...",
    name="CustomAgent",
)

env.reset()
done = False
while not done:
    state, done = env.step()
env.finalize()
eval_result = env.evaluate([env.state.history])
env.shutdown()
```

---

## Evaluation Metrics

| Metric | Description |
|--------|-------------|
| **Internal Responsiveness** | Relevance of answers to questions |
| **Internal Consistency** | Consistency of answers to repeated questions |
| **Internal Harmonic Mean** | Harmonic mean of Responsiveness and Consistency |
| **External Coverage** | Fraction of turns containing at least one verifiable claim (`\|T_c\| / T`) |
| **External Non-refutation Rate** | Macro-averaged per-turn rate of claims not refuted by web evidence |
| **External Consistency (EC)** | Harmonic mean of Coverage and Non-refutation Rate |
| **Inter-session Stability** | Answer stability across sessions |
| **Intra-session Stability** | Answer stability within a session |

---

## License

TBD
