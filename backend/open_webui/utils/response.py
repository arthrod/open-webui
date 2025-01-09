import json
from open_webui.utils.misc import (
    openai_chat_chunk_message_template,
    openai_chat_completion_message_template,
)


def convert_response_ollama_to_openai(ollama_response: dict) -> dict:
    model = ollama_response.get("model", "ollama")
    message_content = ollama_response.get("message", {}).get("content", "")

    response = openai_chat_completion_message_template(model, message_content)
    return response


async def convert_streaming_response_ollama_to_openai(ollama_streaming_response):
    """
    Converts an Ollama streaming response to an OpenAI-compatible streaming response format.
    
    This asynchronous generator function processes streaming responses from Ollama, transforming them into a format compatible with OpenAI's streaming API.
    
    Args:
        ollama_streaming_response: A streaming response object from Ollama containing body iterator.
    
    Yields:
        str: JSON-encoded data chunks representing the streaming response, including:
            - Partial message content
            - Usage statistics when the response is complete
            - A final "[DONE]" marker
    
    Notes:
        - Calculates response and prompt token rates
        - Handles potential division by zero by returning "N/A"
        - Computes approximate total duration in hours, minutes, and seconds
        - Compatible with OpenAI-style streaming response format
    """
    async for data in ollama_streaming_response.body_iterator:
        data = json.loads(data)

        model = data.get("model", "ollama")
        message_content = data.get("message", {}).get("content", "")
        done = data.get("done", False)

        usage = None
        if done:
            usage = {
                "response_token/s": (
                    round(
                        (
                            (
                                data.get("eval_count", 0)
                                / ((data.get("eval_duration", 0) / 10_000_000))
                            )
                            * 100
                        ),
                        2,
                    )
                    if data.get("eval_duration", 0) > 0
                    else "N/A"
                ),
                "prompt_token/s": (
                    round(
                        (
                            (
                                data.get("prompt_eval_count", 0)
                                / ((data.get("prompt_eval_duration", 0) / 10_000_000))
                            )
                            * 100
                        ),
                        2,
                    )
                    if data.get("prompt_eval_duration", 0) > 0
                    else "N/A"
                ),
                "total_duration": data.get("total_duration", 0),
                "load_duration": data.get("load_duration", 0),
                "prompt_eval_count": data.get("prompt_eval_count", 0),
                "prompt_eval_duration": data.get("prompt_eval_duration", 0),
                "eval_count": data.get("eval_count", 0),
                "eval_duration": data.get("eval_duration", 0),
                "approximate_total": (
                    lambda s: f"{s // 3600}h{(s % 3600) // 60}m{s % 60}s"
                )((data.get("total_duration", 0) or 0) // 1_000_000_000),
            }

        data = openai_chat_chunk_message_template(
            model, message_content if not done else None, usage
        )

        line = f"data: {json.dumps(data)}\n\n"
        yield line

    yield "data: [DONE]\n\n"
