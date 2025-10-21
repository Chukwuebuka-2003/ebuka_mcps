from utils import create_server_token, verify_server_token


token = create_server_token("my-server-01")
print("Server token:", token)
