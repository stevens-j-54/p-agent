"""
Pure functions for building the Claude messages array.
"""


def build_messages(thread_history: list, current_message: str) -> list:
    """
    Build the Claude messages array from thread history + current message.

    Merges consecutive same-role messages and drops any leading assistant
    message, since Claude requires the conversation to start with a user turn.
    """
    merged = []
    for msg in thread_history:
        if merged and merged[-1]['role'] == msg['role']:
            merged[-1]['content'] += '\n\n---\n\n' + msg['content']
        else:
            merged.append({'role': msg['role'], 'content': msg['content']})

    if merged and merged[0]['role'] == 'assistant':
        merged = merged[1:]

    merged.append({"role": "user", "content": current_message})
    return merged
