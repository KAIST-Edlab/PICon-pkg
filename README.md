# PICON — Persona Interview & CONsistency Evaluation

PICON is a framework that automatically interviews and evaluates LLM-based personas across three dimensions: **Consistency**, **External Verifiability**, and **Stability**.

Provide your own persona (system prompt), and PICON will interrogate it from multiple angles, analyze the responses, and produce quantitative scores.

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

## Project Structure

```
picon/                      # Package root
├── __init__.py             # Public API: run(), interview(), evaluate()
├── api.py                  # High-level function implementations
├── config.py               # Default settings & resource path helpers
├── schemas.py              # Pydantic data models
├── utils.py                # Utilities (LLM calls, file I/O)
├── agents/                 # Interview/evaluation agents
│   ├── agent_factory.py    # Agent creation factory
│   ├── questioner_agent.py # Question generation
│   ├── extractor_agent.py  # Entity/claim extraction
│   ├── evaluator.py        # Consistency/verification evaluation
│   ├── web_search_agent.py # Web search decision
│   └── prompts/            # System prompts (.txt)
├── env/                    # Interview environment
│   ├── interrogation_env.py
│   └── interviewee_simulator/
│       ├── generic_agent_simulator.py
│       └── simulator_factory.py
└── tools/                  # External tools
    ├── web_search.py       # Serper, Tavily, Google search
    └── address_locator.py  # Google Geocode validation

main.py                     # CLI entry point
servers/                    # Wrapping servers (CharacterAI, HumanSimulacra, etc.)
analysis/                   # Result analysis & visualization
scripts/                    # Run scripts
```

---

## License

TBD
