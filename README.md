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
| **External Coverage** | Fraction of turns containing at least one verifiable claim (`\|T_c\| / T`) |
| **External Non-refutation Rate** | Macro-averaged per-turn rate of claims not refuted by web evidence |
| **External Consistency (EC)** | Harmonic mean of Coverage and Non-refutation Rate |
| **Inter-session Stability** | Answer stability across sessions |
| **Intra-session Stability** | Answer stability within a session |

---

## License

TBD
