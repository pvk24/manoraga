"""Chat with the agent in your terminal:  python cli.py --user pranav"""
import argparse
import os
import sys

import anthropic

from dotenv import load_dotenv

load_dotenv()

from carnatic.agent import CarnaticAgent  # noqa: E402


def handle_command(q: str, agent: CarnaticAgent, curator: bool):
    """Curator commands run here, outside the model, so the agent can never approve its own proposals."""
    from carnatic.catalog import Catalog
    from carnatic.page_import import import_file
    from carnatic.review import describe, edit_command
    parts = q[1:].split()
    if not parts:
        return
    if not curator:
        print("  Curator commands need --curator.\n")
        return
    if parts[0] == "proposals":
        print("\n".join(describe(p) for p in agent.proposals.list("pending")) or "  No pending proposals.", "\n")
    elif parts[0] == "edit":
        res = edit_command(agent.proposals, q[len("/edit"):].strip())
        print(("\n" + describe(agent.proposals.get(res["proposal_id"]))) if res.get("ok") else "  " + res["error"], "\n")
    elif parts[0] == "import" and len(parts) > 1:
        for r in import_file(agent.proposals, q[len("/import"):].strip()):
            print(" ", r)
        agent.catalog = agent.tools.cat = Catalog.load()
        print("  Catalogue reloaded. Rebuild the web page (python scripts/build_web.py) to publish approved changes.\n")
    elif parts[0] in ("approve", "reject") and len(parts) > 1 and parts[1].isdigit():
        res = getattr(agent.proposals, parts[0])(int(parts[1]), " ".join(parts[2:]))
        print(" ", res, "\n")
        if res.get("status") == "approved":   # reload so the change is live in this session
            agent.catalog = agent.tools.cat = Catalog.load()
            print("  Catalogue reloaded. Rebuild the web page (python scripts/build_web.py) to publish it.\n")
    else:
        print("  Commands: /proposals, /edit <id> field=value ..., /approve <id> [note], /reject <id> [note],\n"
              "            /import <file.json>  (the chat page's Review > Export file)\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", default="default")
    p.add_argument("--debug", action="store_true", help="show which tools were called")
    p.add_argument("--curator", action="store_true", help="enable /proposals, /approve <id>, /reject <id>")
    a = p.parse_args()
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or key.startswith("sk-ant-..."):
        sys.exit("No API key found. Copy .env.example to .env and paste your Anthropic API key after ANTHROPIC_API_KEY=")
    agent = CarnaticAgent(user_id=a.user)
    print("ManoRaga — ask about Carnatic music, or tell me how your day went. Type quit (or Ctrl+C) to exit.\n")
    while True:
        try:
            q = input("you > ").strip()
        except (KeyboardInterrupt, EOFError):
            print(); break
        if not q:
            continue
        if q.lower() in ("quit", "exit", "bye"):
            break
        if q.startswith("/"):
            handle_command(q, agent, a.curator)
            continue
        n = len(agent.tools.calls)
        try:
            answer = agent.ask(q)
        except anthropic.AuthenticationError:
            sys.exit("\nYour API key was rejected. Check ANTHROPIC_API_KEY in .env.")
        except anthropic.RateLimitError:
            print("\nToo many requests right now. Wait a minute and try again.\n"); continue
        except anthropic.APIError as e:
            print(f"\nCouldn't reach Claude ({type(e).__name__}). Try again in a moment.\n"); continue
        print("\nmanoraga >", answer)
        if a.debug:
            print(f"  [tools: {agent.tools.calls[n:]}]")
        print()


if __name__ == "__main__":
    main()
