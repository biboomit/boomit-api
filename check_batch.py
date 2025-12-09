"""
Quick script to check OpenAI batch status
"""
import os
from openai import OpenAI

# Initialize client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Batch ID to check
batch_id = "batch_69374745684c8190a6ddcddb29fde115"

print(f"🔍 Checking batch: {batch_id}\n")

try:
    # Retrieve batch
    batch = client.batches.retrieve(batch_id)
    
    print("=" * 60)
    print("BATCH INFORMATION")
    print("=" * 60)
    print(f"ID: {batch.id}")
    print(f"Status: {batch.status}")
    print(f"Created at: {batch.created_at}")
    print(f"Endpoint: {batch.endpoint}")
    print(f"Completion window: {batch.completion_window}")
    print()
    
    print("=" * 60)
    print("REQUEST COUNTS")
    print("=" * 60)
    print(f"Total: {batch.request_counts.total}")
    print(f"Completed: {batch.request_counts.completed}")
    print(f"Failed: {batch.request_counts.failed}")
    print()
    
    print("=" * 60)
    print("FILE IDS")
    print("=" * 60)
    print(f"Input file: {batch.input_file_id}")
    print(f"Output file: {batch.output_file_id}")
    print(f"Error file: {batch.error_file_id}")
    print()
    
    print("=" * 60)
    print("METADATA")
    print("=" * 60)
    if hasattr(batch, 'metadata'):
        metadata = batch.metadata
        if hasattr(metadata, 'model_dump'):
            metadata = metadata.model_dump()
        elif hasattr(metadata, '__dict__'):
            metadata = metadata.__dict__
        
        if metadata:
            for key, value in metadata.items():
                print(f"{key}: {value}")
        else:
            print("No metadata")
    else:
        print("No metadata attribute")
    print()
    
    # Show status details
    if batch.status == "completed":
        print("✅ Batch completed successfully!")
        print(f"Output file available: {batch.output_file_id}")
        
    elif batch.status == "failed":
        print("❌ Batch failed!")
        if batch.error_file_id:
            print(f"Error file available: {batch.error_file_id}")
            
    elif batch.status == "in_progress":
        print("⏳ Batch is in progress...")
        progress = (batch.request_counts.completed / batch.request_counts.total * 100) if batch.request_counts.total > 0 else 0
        print(f"Progress: {batch.request_counts.completed}/{batch.request_counts.total} ({progress:.1f}%)")
        
    elif batch.status == "validating":
        print("🔄 Batch is being validated...")
        
    elif batch.status == "finalizing":
        print("🏁 Batch is finalizing...")
    
    print("\n" + "=" * 60)
    
except Exception as e:
    print(f"❌ Error retrieving batch: {e}")
    print(f"\nError type: {type(e).__name__}")
    print(f"Error details: {str(e)}")
