"""复制到 Dify 的第二个 Python Code 节点，text 绑定 Agent 的最终文本输出。"""
import json


def main(text: str) -> dict:
    text = text.strip()
    # Agent 实际出现过“说明文字 + ```json 代码块”，从对象起点解析。
    start = text.find("{")
    if start < 0:
        raise json.JSONDecodeError("Agent 未返回推荐 JSON，请检查 Agent 最终文本。", text, 0)
    result, end = json.JSONDecoder().raw_decode(text, start)
    # 保留已出现的“空结果 JSON + 候选不足说明”，让后端显示原因。
    trailing = text[end:].strip().removesuffix("```").strip()
    if not result["movie_ids"] and not result.get("error") and trailing:
        result["error"] = trailing
    return {"result": result}
