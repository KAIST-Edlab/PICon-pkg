# PICON — Persona Interview & CONsistency Evaluation

PICON is a framework that automatically interviews and evaluates LLM-based personas across three dimensions: **Consistency**, **External Verifiability**, and **Stability**.

Provide your own persona (system prompt), and PICON will interrogate it from multiple angles, analyze the responses, and produce quantitative scores.

---

## Project Structure

```
picon/                       # Core package
├── __init__.py              #   Public API: run(), interview(), evaluate()
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

main.py                      # CLI entry point
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

## Usage

All baselines are evaluated through `main.py`. Any system that exposes an OpenAI-compatible `/v1/chat/completions` endpoint can be evaluated.

### Prompt-Based (LLM-Generated / DeepPersona / Twin-2K-500)

The persona is defined entirely by a system prompt. Pass it as a string or a `.txt` file path via `--agent_persona`. Works with cloud APIs (routed via litellm) or self-hosted endpoints.

```bash
# Cloud API
python main.py \
    --agent_model gemini/gemini-2.5-flash \
    --agent_persona persona.txt \
    --agent_name "John" \
    --num_turns 20 --num_sessions 2 --do_eval

# Self-hosted vLLM endpoint
python main.py \
    --agent_api_base http://localhost:8000/v1 \
    --agent_model meta-llama/Llama-3-8B \
    --agent_persona "You are a 30-year-old teacher named Jane..." \
    --agent_name "Jane" \
    --num_turns 20 --num_sessions 2 --do_eval
```

### Fine-Tuned Model (OpenCharacter / ConsistentLLM)

Requires a self-hosted model (e.g. vLLM) serving the fine-tuned weights. The persona is baked into the model or passed as a prompt depending on the method.

```bash
# OpenCharacter
python main.py \
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

python main.py \
    --agent_api_base http://localhost:8003/v1 \
    --agent_model consistent_llm \
    --agent_name "John" \
    --num_turns 20 --num_sessions 2 --do_eval
```

### RAG / Multi-Agent (HumanSimulacra)

Uses a wrapping server that orchestrates retrieval-augmented generation over character memories and stories. Character profiles are bundled in `picon/env/personas/human_simulacra/Characters/`.

```bash
# 1) Start the wrapping server
python servers/human_simulacra_server.py \
    --port 8002 \
    --character_name "Mary Jones" \
    --model gemini/gemini-2.5-flash

# 2) Run the interview
python main.py \
    --agent_api_base http://localhost:8002/v1 \
    --agent_model human_simulacra \
    --agent_name "Mary Jones" \
    --num_turns 20 --num_sessions 2 --do_eval
```

### Service (CharacterAI)

Wraps an external service API as an OpenAI-compatible endpoint. No `--agent_persona` needed — the persona is managed by the service.

```bash
# 1) Start the wrapping server
python servers/characterai_server.py \
    --port 8001 \
    --character_id "ZTvEvhHRJs9KEe_NjwHoZEJFAAZ5nUV3UkTaMpNE7rY"

# 2) Run the interview
python main.py \
    --agent_api_base http://localhost:8001/v1 \
    --agent_model characterai \
    --agent_name "Jordan Peterson" \
    --num_turns 20 --num_sessions 2 --do_eval
```

### Custom Persona

You can evaluate any persona agent as long as it speaks through an OpenAI-compatible endpoint. Write your own system prompt and point PICON at any model.

```bash
# Option A: Cloud API with a custom prompt file
python main.py \
    --agent_model gpt-4o \
    --agent_persona my_character.txt \
    --agent_name "My Character" \
    --num_turns 20 --num_sessions 2 --do_eval

# Option B: Your own server (any framework that serves /v1/chat/completions)
python main.py \
    --agent_api_base http://localhost:9000/v1 \
    --agent_model my-custom-model \
    --agent_name "My Agent" \
    --num_turns 20 --num_sessions 2 --do_eval
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
| **External Coverage** | Fraction of turns containing at least one verifiable claim (`\|T_c\| / T`) |
| **External Non-refutation Rate** | Macro-averaged per-turn rate of claims not refuted by web evidence |
| **External Consistency (EC)** | Harmonic mean of Coverage and Non-refutation Rate |
| **Inter-session Stability** | Answer stability across sessions |
| **Intra-session Stability** | Answer stability within a session |

---

## License

TBD
