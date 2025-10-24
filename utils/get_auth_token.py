import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.jwt_util import create_server_token

token = create_server_token("my-server-01")
print("Server token:", token)
