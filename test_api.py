import requests

api_key = "sk- ihxybgmgttcnitodjaouyavnjjoywtazovscecxrzkbsjrux". replace(" ", "")
url = "https://api.siliconflow.cn/v1/chat/completions"

models = [
    "internlm/ internlm2_5-7b-chat",
    "internlm/ internlm2_5-7b- chat",
    "internlm/internlm2_5-7b-chat",
    "Qwen/Qwen2.5-7B-Instruct",
    "deepseek-ai/DeepSeek- V2- Chat"
]

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content- Type": "application/ json"
}

for m in models:
    try:
        r = requests. post(url, headers=headers, json={
            "model": m,
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False
        }, timeout=15)
        print(f"{m}: {r. status_code} - {r.text[:100]}")
    except Exception as e:
        print(f"{m}: Error - {e}")