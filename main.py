"""
Unified interrogation entry point.

All evaluation targets are accessed via the same interface:
  --agent_api_base   OpenAI-compatible API endpoint URL
  --agent_model      Model name at the endpoint
  --agent_persona    System prompt (string or path to .txt file)
  --agent_name       Interviewee name (for output labeling)
  --num_turns        Number of interrogation turns

Examples:
  # Cloud API (litellm routing)
  python main.py --agent_model gemini/gemini-2.5-flash --agent_persona persona.txt --agent_name John

  # Self-hosted vLLM
  python main.py --agent_api_base http://localhost:8000/v1 --agent_model meta-llama/Llama-3-8B --agent_persona "You are ..."

  # Wrapping server (CharacterAI, HumanSimulacra, etc.)
  python main.py --agent_api_base http://localhost:8001/v1 --agent_model characterai --agent_name "Mary Jones"
"""
from picon.utils import setup_logging, read_json, write_json, get_user_input_with_timeout, read_jsonl, get_completion
from picon.env.interrogation_env import InterrogationEnv
from picon.agents.agent_factory import get_agent
from picon.tools.web_search import SerperSearch, TavilySearch
from picon.tools.address_locator import GoogleGeocodeValidate
from dotenv import load_dotenv
import argparse
import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed


def parse_args():
    parser = argparse.ArgumentParser(description="Run interrogation evaluation on any agent endpoint.")
    # Agent endpoint (the evaluation target)
    parser.add_argument('--agent_api_base', type=str, default=None,
                        help='OpenAI-compatible API endpoint URL. If None, litellm routes by model name.')
    parser.add_argument('--agent_api_key', type=str, default=None,
                        help='API key for the agent endpoint (optional).')
    parser.add_argument('--agent_model', type=str, required=True,
                        help='Model name at the agent endpoint.')
    parser.add_argument('--agent_persona', type=str, default=None,
                        help='System prompt / persona description. String or path to .txt file.')
    parser.add_argument('--agent_name', type=str, default='Agent',
                        help='Interviewee name (used in output file naming).')
    # Interrogation agent models
    parser.add_argument('--questioner_model', type=str, default="gpt-5")
    parser.add_argument('--extractor_model', type=str, default="gpt-5.1")
    parser.add_argument('--web_search_model', type=str, default="gpt-5")
    parser.add_argument('--evaluator_model', type=str, default="gemini/gemini-2.5-flash")
    parser.add_argument('--nhd_model', type=str, default="gpt-5-nano")
    # Port settings (for interrogation agents, not the evaluation target)
    parser.add_argument('--questioner_port', type=int, default=None)
    parser.add_argument('--extractor_port', type=int, default=None)
    parser.add_argument('--web_search_port', type=int, default=None)
    parser.add_argument('--evaluator_port', type=int, default=None)
    parser.add_argument('--nhd_port', type=int, default=None)
    # Other configurations
    parser.add_argument('--num_turns', type=int, default=30)
    parser.add_argument('--num_sessions', type=int, default=2)
    parser.add_argument('--max_workers', type=int, default=5)
    parser.add_argument('--question_seed', type=int, default=42)
    parser.add_argument('--log_to_file', action='store_true')
    # Prompt paths
    parser.add_argument('--questioner_prompt_path', type=str, default='picon/agents/prompts/questioner.txt')
    parser.add_argument('--entity_extractor_prompt_path', type=str, default='picon/agents/prompts/entity_extractor.txt')
    parser.add_argument('--claim_extractor_prompt_path', type=str, default='picon/agents/prompts/claim_extractor_prompt.txt')
    parser.add_argument('--web_search_prompt_path', type=str, default='picon/agents/prompts/websearch_prompt.txt')
    parser.add_argument('--evaluator_prompt_path', type=str, default='picon/agents/prompts/evaluator_prompt.txt')
    parser.add_argument('--output_dir', type=str, default='data/results')
    parser.add_argument('--question_file_path', type=str, default='picon/env/wvs_orthogonal_questions.json')
    parser.add_argument('--eval_factors', type=str, nargs='+', default=None,
                        choices=['internal', 'external', 'intra', 'inter'])
    parser.add_argument('--do_eval', action='store_true')

    return parser.parse_args()


def build_interviewee_kwargs(args):
    """Build GenericAgentSimulator kwargs from CLI args."""
    persona = args.agent_persona or ""
    if persona and os.path.isfile(persona):
        with open(persona, 'r') as f:
            persona = f.read()

    return {
        "baseline_name": "generic_agent",
        "model": args.agent_model,
        "api_base": args.agent_api_base,
        "api_key": args.agent_api_key,
        "persona": persona,
        "name": args.agent_name,
        "nhd_model": args.nhd_model,
        "nhd_port": args.nhd_port,
        "question_seed": args.question_seed,
    }


###############################################################################
# Interview & evaluation (same logic as main.py)
###############################################################################

def run_interview(args, interviewee_kwarg):
    """Run interview sessions for a single persona. Returns data needed for evaluation."""
    results_complete = {}
    result_path = f"{args.output_dir}/{args.agent_name}/{interviewee_kwarg.get('name', 'unknown').replace(' ', '_')}_{time.strftime('%Y-%m-%d_%H-%M-%S')}.json"

    persona_stats = {
        "name": interviewee_kwarg.get('name', 'unknown'),
        "ai_detected": False,
        "success": False,
        "error_type": None,
        "duration_min": 0.0,
        "total_cost": 0.0,
        "agents_cost": 0.0,
        "interviewee_cost": 0.0,
        "tool_costs": 0.0,
        "num_interviewee_responses": 0,
        "num_turns_completed": 0,
        "num_tool_calls": 0,
        "sessions_completed": 0,
        "eval_internal_harmonic_mean": None,
        "eval_internal_responsiveness": None,
        "eval_internal_consistency": None,
        "eval_external_wilson": None,
        "eval_stability_inter_session": None,
        "eval_stability_intra_session": None,
    }

    tools = {
        "serper_search": SerperSearch(api_key=os.getenv('SERPER_API_KEY')),
        "google_geocode_validate": GoogleGeocodeValidate(api_key=os.getenv('GOOGLE_GEOCODE'))
    }

    try:
        env = InterrogationEnv(
            agents={
                "questioner": get_agent("questioner", args.questioner_prompt_path, model=args.questioner_model, port=args.questioner_port),
                "extractor": get_agent("entity_extractor", args.entity_extractor_prompt_path, model=args.extractor_model, port=args.extractor_port),
                "web_search": get_agent("web_search", args.web_search_prompt_path, model=args.web_search_model, port=args.web_search_port),
                "evaluator": get_agent("evaluator", args.evaluator_prompt_path, model=args.evaluator_model, port=args.evaluator_port),
            },
            tools=tools,
            max_turns=args.num_turns,
            question_path=args.question_file_path,
            **interviewee_kwarg
        )

        reset_only = False
        histories = []
        for session_idx in range(args.num_sessions):
            logging.info(f"Starting session {session_idx + 1}/{args.num_sessions} for: {interviewee_kwarg.get('name', 'unknown')}")
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

        results_complete["agents_memory"] = {name: agent.memory for name, agent in env.agents.items()}
        write_json(results_complete, result_path)
        logging.info(f"Saved interview results to {result_path}.")

        persona_stats["success"] = True
        for session_key in [k for k in results_complete if k.startswith("session_")]:
            session_data = results_complete[session_key]
            try:
                persona_stats["duration_min"] += float(session_data.get("duration", "0 min").replace(" min", ""))
            except Exception:
                pass
            cost_data = session_data.get("cost", {})
            persona_stats["total_cost"] += cost_data.get("total_cost", 0.0)
            persona_stats["agents_cost"] += cost_data.get("agents_cost", 0.0)
            persona_stats["interviewee_cost"] += cost_data.get("interviewee_cost", 0.0)
            persona_stats["tool_costs"] += sum(cost_data.get("tool_costs", {}).values())
            for turn in session_data.get("history", []):
                for obs in turn.get("environment_observation", []):
                    if obs.get("observation_type") == "interviewee_response":
                        persona_stats["num_interviewee_responses"] += 1
                    if obs.get("observation_type") == "tool_output":
                        tool_outputs = obs.get("tool_output", [])
                        persona_stats["num_tool_calls"] += len(tool_outputs) if tool_outputs else 0
                if turn.get("type") == "main_interrogation":
                    persona_stats["num_turns_completed"] += 1

        return {
            "persona_stats": persona_stats,
            "result_path": result_path,
            "results_complete": results_complete,
            "histories": histories,
            "env": env,
        }

    except ValueError as e:
        if "AI Detected" in str(e):
            persona_stats["ai_detected"] = True
            persona_stats["error_type"] = "AI Detected"
            persona_stats["eval_stability_inter_session"] = 0.0
        else:
            persona_stats["error_type"] = str(e)
        if 'env' in locals():
            env.shutdown()
        return {"persona_stats": persona_stats, "result_path": None, "results_complete": None, "histories": None, "env": None}
    except Exception as e:
        persona_stats["error_type"] = str(e)
        persona_stats["eval_stability_inter_session"] = 0.0
        logging.exception(f"Error for persona {persona_stats['name']}: {e}")
        if 'env' in locals():
            env.shutdown()
        return {"persona_stats": persona_stats, "result_path": None, "results_complete": None, "histories": None, "env": None}


def run_evaluation(interview_result, args):
    """Run evaluation for a single persona's interview results."""
    if interview_result["env"] is None or interview_result["histories"] is None:
        return interview_result["persona_stats"]

    persona_stats = interview_result["persona_stats"]
    result_path = interview_result["result_path"]
    results_complete = interview_result["results_complete"]
    histories = interview_result["histories"]
    env = interview_result["env"]

    try:
        logging.info(f"Running evaluation for {persona_stats['name']}...")
        eval_result = env.evaluate(histories, eval_factors=args.eval_factors)
        results_complete["evaluation"] = eval_result
        write_json(results_complete, result_path)

        if eval_result:
            internal = eval_result.get("internal", {})
            external = eval_result.get("external", {})
            stability = eval_result.get("stability", {})

            internal_score = internal.get("score", {})
            persona_stats["eval_internal_harmonic_mean"] = internal_score.get("harmonic_mean")
            persona_stats["eval_internal_responsiveness"] = internal_score.get("responsiveness_score")
            persona_stats["eval_internal_consistency"] = internal_score.get("consistency_score")

            external_score = external.get("score", {})
            persona_stats["eval_external_wilson"] = external_score.get("wilson_score")

            inter_session = stability.get("inter_session", {})
            intra_session = stability.get("intra_session", {})
            persona_stats["eval_stability_inter_session"] = inter_session.get("score")
            persona_stats["eval_stability_intra_session"] = intra_session.get("score")

    except Exception as e:
        logging.exception(f"Evaluation failed for {persona_stats['name']}: {e}")
        persona_stats["eval_stability_inter_session"] = 0.0
    finally:
        env.shutdown()

    return persona_stats


###############################################################################
# Main
###############################################################################

if __name__ == "__main__":
    args = parse_args()
    setup_logging(log_to_file=args.log_to_file, process_name="main")
    load_dotenv()

    interviewee_kwarg = build_interviewee_kwargs(args)
    logging.info(f"Target: {args.agent_name} @ {args.agent_api_base or 'litellm'} / {args.agent_model}")

    # Run interview
    result = run_interview(args, interviewee_kwarg)
    persona_stats = result["persona_stats"]

    # Run evaluation if requested
    if args.do_eval and result["env"] is not None:
        persona_stats = run_evaluation(result, args)

    # Save summary
    summary_path = f"{args.output_dir}/{args.agent_name.replace(' ', '_')}/summary_{time.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)

    summary = {
        "agent_name": args.agent_name,
        "agent_model": args.agent_model,
        "agent_api_base": args.agent_api_base,
        "run_timestamp": time.strftime('%Y-%m-%d_%H-%M-%S'),
        "config": {
            "questioner_model": args.questioner_model,
            "evaluator_model": args.evaluator_model,
            "nhd_model": args.nhd_model,
            "num_turns": args.num_turns,
            "num_sessions": args.num_sessions,
        },
        "results": persona_stats,
    }
    write_json(summary, summary_path)

    # Log results
    logging.info("=" * 60)
    logging.info(f"RESULT: {args.agent_name}")
    logging.info("=" * 60)
    logging.info(f"Success: {persona_stats.get('success')}")
    logging.info(f"AI Detected: {persona_stats.get('ai_detected')}")
    logging.info(f"Duration: {persona_stats.get('duration_min', 0):.2f} min")
    logging.info(f"Cost: ${persona_stats.get('total_cost', 0):.4f}")
    logging.info(f"Turns: {persona_stats.get('num_turns_completed', 0)}")
    logging.info(f"Summary saved to: {summary_path}")
    logging.info("=" * 60)
