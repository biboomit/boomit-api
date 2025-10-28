from app.core.config import OpenAIConfig

class OpenAIBatchIntegration:
    """Integration class for handling batch operations with OpenAI."""

    def __init__(self):
        self.api_key = OpenAIConfig().get_api_key()
        
    def process_using_batches(self, data):
        """Process a batch of data using OpenAI API."""

        batches = self._create_batches(data)
        
        jsonl_file = self._create_upload_file(batches)

        ...

    def _create_batches(self, data: list[tuple[str, int]]) -> list[list[tuple[str, int]]]:
        """Create batches from the input data."""
        data_batches = []
        batch_size = OpenAIConfig().get_batch_size()

        for i in range(0, len(data), batch_size):
            data_batches.append(data[i:i + batch_size])

        return data_batches

    def _create_upload_file(self, batches: list[list[tuple[str, int]]]) -> str:
        """Create a JSONL file from the batches."""
        lines = []
    
        # Flatten all batches and create JSONL lines
        for batch_idx, batch in enumerate(batches):
            for item_idx, (text, item_id) in enumerate(batch):
                # Create the request body following OpenAI batch format
                body = {
                    "model": OpenAIConfig().get_model(),
                    "input": [
                        {"role": "system", "content": OpenAIConfig().get_system_prompt()},  # Assuming you have this
                        {"role": "user", "content": text}
                    ],
                    "text": {
                        "format": ... # TODO: specify the desired response format
                    },
                    "prompt_cache_key": "review_analysis_v1"
                }
                
                # Create the batch request line
                request_line = {
                    "custom_id": f"batch-{batch_idx}-item-{item_id}",  # Unique identifier
                    "method": "POST",
                    "url": "/v1/chat/completions",  # Standard OpenAI endpoint
                    "body": body
                }
                
                lines.append(request_line)
            
        
