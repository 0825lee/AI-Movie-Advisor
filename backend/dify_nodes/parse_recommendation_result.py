"""复制到 Dify 的第二个 Python Code 节点，text 绑定 Agent 的最终文本输出。"""
import json


def main(text: str) -> dict:
    text = text.strip()
    result, end = json.JSONDecoder().raw_decode(text)
    # 保留已出现的“空结果 JSON + 候选不足说明”，让后端显示原因。
    if not result["movie_ids"] and not result.get("error") and text[end:].strip():
        result["error"] = text[end:].strip()
    return {"result": result}
