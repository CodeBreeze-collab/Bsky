import json
import re
from pathlib import Path
from pypdf import PdfReader


def process_pdf_folder(
    folder_path: str, output_jsonl_name: str = 'stores.jsonl'
):
  """Processes all .pdf files in the given folder path,

  extracts store URLs, IDs, and optional affiliate percentages,
  and writes them out to a .jsonl file.
  """
  input_dir = Path(folder_path)

  if not input_dir.exists() or not input_dir.is_dir():
    print(f'Error: The path "{folder_path}" is not a valid directory.')
    return

  pdf_files = list(input_dir.glob('*.pdf'))
  if not pdf_files:
    print(f'No .pdf files found in "{folder_path}".')
    return

  all_stores = []
  seen_stores = set()

  # Domain validation regex
  domain_regex = re.compile(
      r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b'
  )

  # Regex to locate percentage values (e.g., 10%, 5.5%)
  percentage_regex = re.compile(r'(\d+(?:\.\d+)?)\s*%')

  for file_path in pdf_files:
    try:
      reader = PdfReader(file_path)
      text = ''
      for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
          text += page_text + '\n'

      # Split text by 'ID:' to isolate each store block cleanly
      chunks = text.split('ID:')
      file_count = 0

      for i in range(1, len(chunks)):
        id_match = re.match(r'\s*(\d+)', chunks[i])
        if not id_match:
          continue
        store_id = id_match.group(1)

        # Inspect the preceding chunk for the store URL
        prev_text = chunks[i - 1]
        lines = [line.strip() for line in prev_text.splitlines() if line.strip()]

        found_url = None
        for line in reversed(lines[-5:]):
          tokens = line.split()
          for token in reversed(tokens):
            clean_token = token.strip('()[]{}<>.,;:"\'')
            if domain_regex.match(clean_token) and clean_token.lower() not in [
                'approved',
                'pending',
            ]:
              found_url = clean_token
              break
          if found_url:
            break

        # Search the store's text block for an affiliate/commission percentage
        block_text = prev_text + ' ID:' + chunks[i]
        pct_match = percentage_regex.search(block_text)
        affiliate_percentage = pct_match.group(0) if pct_match else None

        if found_url and store_id:
          unique_key = (found_url, store_id)
          if unique_key not in seen_stores:
            seen_stores.add(unique_key)
            all_stores.append({
                'store_url': found_url,
                'store_id': store_id,
                'affiliate_percentage': affiliate_percentage,
                'source_pdf': file_path.name,
            })
            file_count += 1

      print(
          f'Successfully processed PDF: {file_path.name} (Extracted'
          f' {file_count} stores)'
      )

    except Exception as e:
      print(f'Error processing {file_path.name}: {e}')

  # Write all extracted records to a .jsonl file
  output_path = input_dir / output_jsonl_name
  with open(output_path, 'w', encoding='utf-8') as f:
    for store in all_stores:
      f.write(json.dumps(store) + '\n')

  print(
      f'\nSuccessfully wrote {len(all_stores)} unique stores to:'
      f' {output_path.absolute()}'
  )


if __name__ == '__main__':
  target_folder_path = '/Users/hdon/Desktop/go-affpro-pages/goaffpro-my-stores/'
  process_pdf_folder(target_folder_path, 'extracted_my_stores_with_pct.jsonl')