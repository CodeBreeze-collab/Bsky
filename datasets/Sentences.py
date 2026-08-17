import os
import re
from pathlib import Path


def split_into_ences(text: str) -> list[str]:
  """Splits text into sentences using a standard regular expression.

  Handles sentence boundaries (. ! ?) followed by whitespace or newlines.
  """
  sentence_pattern = re.compile(r'(?<=[.!?])\s+|\n+')
  sentences = sentence_pattern.split(text.strip())
  return [s.strip() for s in sentences if s.strip()]


def process_folder(folder_path: str):
  """Processes all .txt files in the given folder path,

  writing each out to a corresponding _sentences.txt file.
  """
  input_dir = Path(folder_path)

  if not input_dir.exists() or not input_dir.is_dir():
    print(f'Error: The path "{folder_path}" is not a valid directory.')
    return

  # Find all .txt files in the directory
  txt_files = list(input_dir.glob('*.txt'))

  if not txt_files:
    print(f'No .txt files found in "{folder_path}".')
    return

  for file_path in txt_files:
    # Skip files that are already output files
    if file_path.name.endswith('_sentences.txt'):
      continue

    try:
      # Read the input text file with UTF-8 encoding
      with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

      # Extract sentences
      sentences = split_into_ences(content)

      # Create output filename (e.g., sample.txt -> sample_sentences.txt)
      output_filename = f'{file_path.stem}_sentences.txt'
      output_path = input_dir / output_filename

      # Write each sentence on a new line
      with open(output_path, 'w', encoding='utf-8') as f:
        for sentence in sentences:
          f.write(sentence + '\n')

      print(
          f'Successfully processed: {file_path.name} -> {output_filename}'
          f' ({len(sentences)} sentences)'
      )

    except Exception as e:
      print(f'Error processing {file_path.name}: {e}')


if __name__ == '__main__':
  # Replace with your target folder path (can be relative or absolute)
  target_folder_path = '/Users/hdon/Desktop/Desktop-05-18/how-did/01-18-2025-Desktop/Desktop-01-08-2026/DS-12-15-2025/Desktop-to-sort/Removed/st/valkyrie/stories_all/dreadnaught-all/'
  process_folder(target_folder_path)