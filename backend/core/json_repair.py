"""
🔥 P4新增: JSON修复工具 (Robust JSON Parser)

功能:
1. 自动修复LLM输出中的JSON格式错误
2. 处理DeepSeek-R1的<think>块
3. 修复常见的JSON语法错误
4. 提供多层次的解析策略

使用场景:
- 所有Agent解析LLM输出时调用
- 替代简单的json.loads()
"""

import re
import json
from typing import Any, Dict, Optional, Tuple


class JSONRepairError(Exception):
    """JSON修复失败异常"""
    pass


def repair_and_parse(text: str, strict: bool = False) -> Tuple[Dict, str]:
    """
    修复并解析JSON

    多层次解析策略:
    1. 预处理: 移除<think>块和Markdown代码块
    2. 直接解析: 尝试标准json.loads
    3. 语法修复: 修复常见错误
    4. 激进修复: 重新提取JSON结构
    5. 部分提取: 提取可解析的部分

    Args:
        text: 原始文本
        strict: 是否严格模式 (严格模式下不做激进修复)

    Returns:
        (parsed_dict, repair_method) 元组

    Raises:
        JSONRepairError: 所有修复方法都失败时
    """
    original_text = text

    # 阶段1: 预处理
    text = _preprocess(text)

    # 阶段2: 直接解析
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result, "direct"
    except json.JSONDecodeError:
        pass

    # 阶段3: 提取JSON块
    json_text = _extract_json_block(text)
    if json_text:
        try:
            result = json.loads(json_text)
            if isinstance(result, dict):
                return result, "extract_block"
        except json.JSONDecodeError:
            text = json_text  # 使用提取的块继续修复

    # 阶段4: 语法修复
    repaired = _fix_common_errors(text)
    try:
        result = json.loads(repaired)
        if isinstance(result, dict):
            return result, "syntax_fix"
    except json.JSONDecodeError:
        pass

    if strict:
        raise JSONRepairError(f"严格模式下无法解析JSON: {text[:200]}...")

    # 阶段5: 激进修复
    aggressive_result = _aggressive_repair(text)
    if aggressive_result:
        return aggressive_result, "aggressive"

    # 阶段6: 部分提取
    partial = _extract_partial(text)
    if partial:
        return partial, "partial"

    raise JSONRepairError(f"所有修复方法都失败: {original_text[:200]}...")


def clean_llm_output(text: str) -> str:
    """
    清理LLM输出

    专门处理DeepSeek-R1等Reasoner模型的输出
    """
    return _preprocess(text)


def _preprocess(text: str) -> str:
    """预处理文本"""
    # 1. 移除<think>块
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    # 2. 移除Markdown代码块标记
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)

    # 3. 移除开头的非JSON文本
    text = re.sub(r'^[^\[{]*(?=[\[{])', '', text.strip())

    # 4. 移除结尾的非JSON文本
    text = re.sub(r'[\]}][^\]}]*$', lambda m: m.group()[0], text)

    return text.strip()


def _extract_json_block(text: str) -> Optional[str]:
    """提取JSON块"""
    # 尝试找到第一个完整的JSON对象
    brace_count = 0
    start = -1

    for i, char in enumerate(text):
        if char == '{':
            if start == -1:
                start = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start != -1:
                return text[start:i+1]

    # 如果没找到完整的，返回从第一个{开始的部分
    if start != -1:
        return text[start:]

    return None


def _fix_common_errors(text: str) -> str:
    """修复常见的JSON语法错误"""

    # 1. 修复尾随逗号
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)

    # 2. 修复未转义的换行符 (只在字符串内部)
    # 这个比较复杂，我们用一个简化的方法
    text = _fix_newlines_in_strings(text)

    # 3. 修复单引号
    text = _convert_single_quotes(text)

    # 4. 修复缺少的引号
    text = _fix_missing_quotes(text)

    # 5. 修复Python风格的布尔值和None
    text = text.replace('True', 'true')
    text = text.replace('False', 'false')
    text = text.replace('None', 'null')

    # 6. 移除注释
    text = re.sub(r'//.*?(?=\n|$)', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    return text


def _fix_newlines_in_strings(text: str) -> str:
    """修复字符串内的换行符"""
    result = []
    in_string = False
    escape_next = False
    i = 0

    while i < len(text):
        char = text[i]

        if escape_next:
            result.append(char)
            escape_next = False
            i += 1
            continue

        if char == '\\':
            escape_next = True
            result.append(char)
            i += 1
            continue

        if char == '"':
            in_string = not in_string
            result.append(char)
            i += 1
            continue

        if in_string and char == '\n':
            result.append('\\n')
        elif in_string and char == '\r':
            result.append('\\r')
        elif in_string and char == '\t':
            result.append('\\t')
        else:
            result.append(char)

        i += 1

    return ''.join(result)


def _convert_single_quotes(text: str) -> str:
    """将单引号转换为双引号 (小心处理字符串内的情况)"""
    result = []
    in_double_string = False
    in_single_string = False
    escape_next = False

    for char in text:
        if escape_next:
            result.append(char)
            escape_next = False
            continue

        if char == '\\':
            escape_next = True
            result.append(char)
            continue

        if char == '"' and not in_single_string:
            in_double_string = not in_double_string
            result.append(char)
            continue

        if char == "'" and not in_double_string:
            in_single_string = not in_single_string
            result.append('"')  # 转换为双引号
            continue

        result.append(char)

    return ''.join(result)


def _fix_missing_quotes(text: str) -> str:
    """修复缺少引号的键"""
    # 匹配 {key: 或 ,key: 的模式，给key加上引号
    pattern = r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:'
    text = re.sub(pattern, r'\1"\2":', text)
    return text


def _aggressive_repair(text: str) -> Optional[Dict]:
    """
    激进修复模式

    尝试从文本中提取关键信息重建JSON
    """
    # 查找所有的键值对模式
    kv_pattern = r'"([^"]+)"\s*:\s*("(?:[^"\\]|\\.)*"|[\d.]+|true|false|null|\[.*?\]|\{.*?\})'

    matches = re.findall(kv_pattern, text, re.DOTALL)

    if not matches:
        return None

    result = {}
    for key, value in matches:
        try:
            # 尝试解析值
            parsed_value = json.loads(value)
            result[key] = parsed_value
        except json.JSONDecodeError:
            # 如果值解析失败，作为字符串保存
            result[key] = value.strip('"')

    return result if result else None


def _extract_partial(text: str) -> Optional[Dict]:
    """
    部分提取模式

    提取可以解析的部分
    """
    # 尝试逐步截断
    for end in range(len(text), 10, -10):
        truncated = text[:end]

        # 补全括号
        open_braces = truncated.count('{') - truncated.count('}')
        open_brackets = truncated.count('[') - truncated.count(']')

        completed = truncated + ']' * max(0, open_brackets) + '}' * max(0, open_braces)

        try:
            result = json.loads(completed)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue

    return None


def safe_json_loads(text: str, default: Any = None) -> Any:
    """
    安全的JSON解析

    失败时返回默认值而不是抛出异常
    """
    try:
        result, _ = repair_and_parse(text)
        return result
    except JSONRepairError:
        return default


def extract_json_from_response(response: str, key: str = None) -> Any:
    """
    从LLM响应中提取JSON并可选地获取特定键

    Args:
        response: LLM响应文本
        key: 可选，要提取的特定键

    Returns:
        解析后的JSON或特定键的值
    """
    try:
        result, _ = repair_and_parse(response)
        if key and isinstance(result, dict):
            return result.get(key)
        return result
    except JSONRepairError:
        return None


# 便捷函数: 替代各Agent中的_clean_json方法
def clean_json(text: str) -> str:
    """
    清理JSON文本 (供各Agent使用)

    这是一个向后兼容的函数，返回清理后的字符串
    """
    text = _preprocess(text)
    text = _fix_common_errors(text)
    return text
