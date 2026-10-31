"""复制到 Dify 的第二个 Python Code 节点，text 绑定 Agent 的最终文本输出。"""
import json


def main(text: str) -> dict:
    return {"result": json.loads(text)}
