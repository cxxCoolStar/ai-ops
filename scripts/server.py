import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai_ops.server.http_server import serve


if __name__ == "__main__":
    serve()
