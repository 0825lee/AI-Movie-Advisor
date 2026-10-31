"""复制到 Dify 的第一个 Python Code 节点，text 绑定需求解析 LLM.text。"""
import json


def main(text: str) -> dict:
    return {"criteria_json": json.dumps(json.loads(text), ensure_ascii=False)}
