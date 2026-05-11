import requests
api_key = "sk-ihxybgmgttcnitodjaouyavnjjoywtazovscecxrzkbsjrux"
url = "https://api.siliconflow.cn/v1/chat/completions"
models = [
    "internlm/internlm2_5-7b-chat",
    "Qwen/Qwen2.5-7B-Instruct"
]

headers = {
    "Authorization": "Bearer " + api_key,
    "Content-Type": "application/json"
}

for m in models:
    try:
        r = requests.post(url, headers=headers, json={
            "model": m,
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False
        }, timeout=15)
        print(m + ": " + str(r.status_code) + " - " + r.text[:100])
    except Exception as e:
        print(m + ": Error - " + str(e))