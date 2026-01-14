import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai_ops.agent.agent import parse_args, run_agent


if __name__ == "__main__":
    run_agent(parse_args())

