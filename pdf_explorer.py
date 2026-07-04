import os
import requests
import tiktoken
import argparse
from markitdown import MarkItDown
from pathlib import Path

def find_pdf_files(root_folder):
    pdf_files = []
    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(dirpath, filename))
    return pdf_files

def convert_pdf_to_text(pdf_path):
    """Convert a PDF file to text using markitdown."""
    try:
        md = MarkItDown()
        result = md.convert(pdf_path)
        return result.text_content
    except Exception as e:
        print(f"Error converting {pdf_path}: {e}")
        return ""

def estimate_tokens(text, model="gpt-3.5-turbo"):
    """Estimate token count for given text."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        # Fallback approximation: roughly 4 characters per token
        return len(text) // 4

def calculate_costs(tokens):
    """Calculate estimated costs for popular LLM models."""
    costs = {
        "GPT-3.5 Turbo": {"input": 0.0015 / 1000, "output": 0.002 / 1000},
        "GPT-4": {"input": 0.03 / 1000, "output": 0.06 / 1000},
        "GPT-4 Turbo": {"input": 0.01 / 1000, "output": 0.03 / 1000},
        "Claude 3.5 Sonnet": {"input": 0.003 / 1000, "output": 0.015 / 1000},
        "Claude 3 Haiku": {"input": 0.00025 / 1000, "output": 0.00125 / 1000}
    }
    
    print(f"\nEstimated costs for {tokens:,} tokens:")
    print("=" * 50)
    for model, pricing in costs.items():
        input_cost = tokens * pricing["input"]
        # Assume 25% output tokens for processing
        output_tokens = tokens * 0.25
        output_cost = output_tokens * pricing["output"]
        total_cost = input_cost + output_cost
        print(f"{model:<20}: ${total_cost:.4f} (input: ${input_cost:.4f}, output: ${output_cost:.4f})")
    print("=" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF to text converter and token counter")
    parser.add_argument("--single-file", type=str, help="Analyze a single PDF file and return token count")
    args = parser.parse_args()
    
    if args.single_file:
        # Single file analysis mode
        pdf_path = args.single_file
        if not os.path.exists(pdf_path):
            print(f"Error: File '{pdf_path}' not found.")
            exit(1)
        
        if not pdf_path.lower().endswith('.pdf'):
            print(f"Error: '{pdf_path}' is not a PDF file.")
            exit(1)
        
        print(f"Analyzing: {os.path.basename(pdf_path)}")
        text_content = convert_pdf_to_text(pdf_path)
        
        if text_content:
            tokens = estimate_tokens(text_content)
            print(f"Characters: {len(text_content):,}")
            print(f"Tokens: {tokens:,}")
            calculate_costs(tokens)
        else:
            print("Failed to extract text from PDF.")
            exit(1)
    else:
        # Original batch processing mode
        # Set your folder path and webhook URL here
        folder_path = "/mnt/c/Users/victo/OneDrive/Documents/Learning/cours_CS/"
        webhook_url = "http://localhost:5678/webhook-test/5a285628-7860-4676-99ba-cee20e2c4f10"

        pdf_files = find_pdf_files(folder_path)
        print(f"Found {len(pdf_files)} PDF files.")

        if not pdf_files:
            print("No PDF files found in the specified directory.")
            exit()

        all_text = ""
        total_tokens = 0
        successful_conversions = 0

        print("\nProcessing PDFs...")
        for i, pdf_file in enumerate(pdf_files, 1):
            print(f"[{i}/{len(pdf_files)}] Converting: {os.path.basename(pdf_file)}")
            
            text_content = convert_pdf_to_text(pdf_file)
            if text_content:
                tokens = estimate_tokens(text_content)
                total_tokens += tokens
                all_text += text_content + "\n\n"
                successful_conversions += 1
                print(f"  → {tokens:,} tokens extracted")
            else:
                print(f"  → Failed to convert")

        print(f"\nConversion Summary:")
        print(f"Successfully converted: {successful_conversions}/{len(pdf_files)} PDFs")
        print(f"Total characters: {len(all_text):,}")
        print(f"Total tokens: {total_tokens:,}")
        
        if total_tokens > 0:
            calculate_costs(total_tokens)
            
            # Save the combined text if needed
            output_file = "combined_pdfs_text.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(all_text)
            print(f"\nCombined text saved to: {output_file}")
        else:
            print("No text extracted from any PDFs.")
