import os, sys, time, urllib.request, socket
from urllib.parse import urlsplit

litellm_url = os.environ.get("LITELLM_BASE_URL", "http://litellm:4000") + "/health/liveliness"
milvus_uri = urlsplit(os.environ.get("MILVUS_URI", "http://milvus:19530"))
milvus_host = milvus_uri.hostname
milvus_port = milvus_uri.port or 19530

print("Waiting for LiteLLM Gateway...")
while True:
    try:
        req = urllib.request.Request(litellm_url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                print("LiteLLM is Ready.")
                break
    except Exception as e:
        print(f"LiteLLM not ready yet ({e}), waiting 2s...")
        time.sleep(2)

print("Waiting for Milvus Standalone...")
while True:
    try:
        with socket.create_connection((milvus_host, milvus_port), timeout=3):
            print("Milvus is Ready.")
            break
    except Exception as e:
        print(f"Milvus not ready yet ({e}), waiting 2s...")
        time.sleep(2)

print("All platform dependencies ready!")
