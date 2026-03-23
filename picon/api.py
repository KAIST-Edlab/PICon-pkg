"""
PICON high-level API.

Usage:
    import picon

    result = picon.run(
        persona="You are a 35-year-old software engineer...",
        name="John",
        model="gemini/gemini-2.5-flash",
    )
    print(result.summary)
    print(result.eval_scores)
    result.save("results/john.json")
"""

from dataclasses import dataclass, field
from typing import Optional, List
import os
import time
import logging

from dotenv import load_dotenv

from picon.config import DEFAULT_CONFIG, get_prompt_path, get_question_path
from picon.agents.agent_factory import get_agent
from picon.env.interrogation_env import InterrogationEnv
from picon.tools.web_search import SerperSearch
from picon.tools.address_locator import GoogleGeocodeValidate
from picon.utils import write_json, read_json


@dataclass
class PiconResult:
    """Interview + evaluation result container."""
    success: bool = False
    ai_detected: bool = False
    summary: dict = field(default_factory=dict)
    eval_scores: dict = field(default_factory=dict)
    raw_results: dict = field(default_factory=dict)
    result_path: Optional[str] = None

    def save(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        write_json(self.raw_results, path)


def run(
    persona: str,
    name: str = "Agent",
    model: str = "gemini/gemini-2.5-flash",
    api_base: str = None,
    api_key: str = None,
    num_turns: int = 30,
    num_sessions: int = 2,
    do_eval: bool = True,
    eval_factors: List[str] = None,
    questioner_model: str = None,
    extractor_model: str = None,
    web_search_model: str = None,
    evaluator_model: str = None,
    nhd_model: str = None,
    output_dir: str = None,
    question_seed: int = 42,
    **kwargs,
) -> PiconResult:
    """Run persona interview + evaluation in one call."""
    load_dotenv()

    cfg = {**DEFAULT_CONFIG}
    if questioner_model:  cfg["questioner_model"] = questioner_model
    if extractor_model:   cfg["extractor_model"] = extractor_model
    if web_search_model:  cfg["web_search_model"] = web_search_model
    if evaluator_model:   cfg["evaluator_model"] = evaluator_model
    if nhd_model:         cfg["nhd_model"] = nhd_model
    if output_dir:        cfg["output_dir"] = output_dir

    # Read persona from file if path is given
    if persona and os.path.isfile(persona):
        with open(persona) as f:
            persona = f.read()

    interviewee_kwargs = {
        "baseline_name": "generic_agent",
        "model": model,
        "api_base": api_base,
        "api_key": api_key,
        "persona": persona or "",
        "name": name,
        "nhd_model": cfg["nhd_model"],
        "question_seed": question_seed,
        **kwargs,
    }

    # Build agents
    agents = {
        "questioner": get_agent("questioner", get_prompt_path("questioner.txt"), model=cfg["questioner_model"]),
        "extractor": get_agent("claim_extractor", get_prompt_path("claim_extractor_prompt.txt"), model=cfg["extractor_model"]),
        "web_search": get_agent("web_search", get_prompt_path("websearch_prompt.txt"), model=cfg["web_search_model"]),
        "evaluator": get_agent("evaluator", get_prompt_path("evaluator_prompt.txt"), model=cfg["evaluator_model"]),
    }

    tools = {
        "serper_search": SerperSearch(api_key=os.getenv("SERPER_API_KEY")),
        "google_geocode_validate": GoogleGeocodeValidate(api_key=os.getenv("GOOGLE_GEOCODE")),
    }

    result_dir = cfg["output_dir"]
    result_path = f"{result_dir}/{name.replace(' ', '_')}_{time.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)

    picon_result = PiconResult()
    persona_stats = {
        "name": name,
        "ai_detected": False,
        "success": False,
        "total_cost": 0.0,
        "sessions_completed": 0,
    }

    try:
        env = InterrogationEnv(
            agents=agents,
            tools=tools,
            max_turns=num_turns,
            question_path=get_question_path(),
            **interviewee_kwargs,
        )

        results_complete = {}
        histories = []
        reset_only = False
        for session_idx in range(num_sessions):
            logging.info(f"Starting session {session_idx + 1}/{num_sessions} for: {name}")
            env.reset(reset_only=reset_only)
            if not reset_only:
                done = False
                while not done:
                    state, done = env.step()
                state = env.finalize()
            session_result = env.save_state()
            histories.append(env.state.history)
            results_complete[f"session_{session_idx+1}"] = session_result
            persona_stats["sessions_completed"] += 1
            reset_only = True

        results_complete["agents_memory"] = {n: agent.memory for n, agent in env.agents.items()}
        write_json(results_complete, result_path)

        persona_stats["success"] = True
        # Aggregate costs
        for session_key in [k for k in results_complete if k.startswith("session_")]:
            cost_data = results_complete[session_key].get("cost", {})
            persona_stats["total_cost"] += cost_data.get("total_cost", 0.0)

        # Evaluation
        eval_scores = {}
        if do_eval:
            logging.info(f"Running evaluation for {name}...")
            eval_result = env.evaluate(histories, eval_factors=eval_factors)
            results_complete["evaluation"] = eval_result
            write_json(results_complete, result_path)

            if eval_result:
                internal = eval_result.get("internal", {}).get("score", {})
                external = eval_result.get("external", {}).get("score", {})
                stability = eval_result.get("stability", {})
                eval_scores = {
                    "internal_harmonic_mean": internal.get("harmonic_mean"),
                    "internal_responsiveness": internal.get("responsiveness_score"),
                    "internal_consistency": internal.get("consistency_score"),
                    "external_wilson": external.get("wilson_score"),
                    "inter_session_stability": stability.get("inter_session", {}).get("score"),
                    "intra_session_stability": stability.get("intra_session", {}).get("score"),
                }

        env.shutdown()

        picon_result.success = True
        picon_result.summary = persona_stats
        picon_result.eval_scores = eval_scores
        picon_result.raw_results = results_complete
        picon_result.result_path = result_path
        return picon_result

    except ValueError as e:
        if "AI Detected" in str(e):
            picon_result.ai_detected = True
        logging.warning(f"Interview stopped: {e}")
        if "env" in locals():
            env.shutdown()
        picon_result.summary = persona_stats
        return picon_result

    except Exception as e:
        logging.exception(f"Error during interview: {e}")
        if "env" in locals():
            env.shutdown()
        picon_result.summary = persona_stats
        return picon_result


def interview(persona: str, name: str = "Agent", **kwargs) -> PiconResult:
    """Run interview only (no evaluation)."""
    return run(persona=persona, name=name, do_eval=False, **kwargs)


def evaluate(result_path: str, eval_factors: List[str] = None, evaluator_model: str = None) -> dict:
    """Run evaluation on an existing interview result file."""
    load_dotenv()

    cfg = {**DEFAULT_CONFIG}
    if evaluator_model:
        cfg["evaluator_model"] = evaluator_model

    results = read_json(result_path)

    agents = {
        "evaluator": get_agent("evaluator", get_prompt_path("evaluator_prompt.txt"), model=cfg["evaluator_model"]),
    }

    env = InterrogationEnv(
        agents=agents,
        result_data=results,
    )

    histories = []
    for key in sorted(k for k in results if k.startswith("session_")):
        session = results[key]
        from picon.schemas import Turn
        history = [Turn(**t) for t in session.get("history", [])]
        histories.append(history)

    eval_result = env.evaluate(histories, eval_factors=eval_factors)
    env.shutdown()

    # Save back
    results["evaluation"] = eval_result
    write_json(results, result_path)

    if eval_result:
        internal = eval_result.get("internal", {}).get("score", {})
        external = eval_result.get("external", {}).get("score", {})
        stability = eval_result.get("stability", {})
        return {
            "internal_harmonic_mean": internal.get("harmonic_mean"),
            "internal_responsiveness": internal.get("responsiveness_score"),
            "internal_consistency": internal.get("consistency_score"),
            "external_wilson": external.get("wilson_score"),
            "inter_session_stability": stability.get("inter_session", {}).get("score"),
            "intra_session_stability": stability.get("intra_session", {}).get("score"),
        }
    return {}
