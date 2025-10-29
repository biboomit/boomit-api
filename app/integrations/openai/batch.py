import io
import json
from app.core.config import OpenAIConfig
from openai import OpenAI
from openai.lib._parsing._responses import type_to_text_format_param


class OpenAIBatchIntegration:
    """Integration class for handling batch operations with OpenAI."""

    def __init__(self):
        self.api_key = OpenAIConfig().get_api_key()

    def process_using_batches(self, data):
        """Process a batch of data using OpenAI API."""

        batches = self._create_batches(data)

        jsonl_file = self._create_upload_file(batches)

        uploaded, batch = self._upload_and_create_batch(jsonl_file)

        return uploaded, batch

    def _create_batches(
        self, data: list[tuple[str, int]]
    ) -> list[list[tuple[str, int]]]:
        """Create batches from the input data."""
        data_batches = []
        batch_size = OpenAIConfig().get_batch_size()

        for i in range(0, len(data), batch_size):
            data_batches.append(data[i : i + batch_size])

        return data_batches

    def _create_upload_file(self, batches: list[list[tuple[str, int]]]) -> str:
        """Create a JSONL file from the batches."""
        lines = []

        # Flatten all batches and create JSONL lines
        for batch_idx, batch in enumerate(batches):
            for item_idx, (content, score) in enumerate(batch):
                # Create the request body following OpenAI batch format
                raise NotImplementedError(
                    "Specify the desired response format in the body."
                )
                body = {
                    "model": OpenAIConfig().get_model(),
                    "input": [
                        {
                            "role": "system",
                            "content": OpenAIConfig().get_system_prompt(),
                        },
                        {"role": "user", "content": f"{score}: {content}"},
                    ],
                    "text": {
                        "format": ...  # TODO: specify the desired response format
                    },
                    "prompt_cache_key": "review_analysis_v1",
                }

                # Create the batch request line
                request_line = {
                    "custom_id": f"batch-review-{batch_idx}-item-{item_idx}",
                    "method": "POST",
                    "url": "/v1/responses",
                    "body": body,
                }

                lines.append(request_line)

        # Convert lines to JSONL format and return
        return "\n".join(json.dumps(line) for line in lines)

    def _upload_and_create_batch(self, jsonl_file: str):
        client = OpenAI(api_key=self.api_key)

        uploaded_file = client.files.create(
            file=io.BytesIO(jsonl_file.encode("utf-8")),
            purpose="batch",
        )

        batch = client.batches.create(
            input_file_id=uploaded_file.id,
            endpoint="/v1/responses",
            completion_window="24h",
            metadata={"job": "review_analysis_v1"},
        )

        return uploaded_file, batch
