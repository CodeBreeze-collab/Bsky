import os
from pypdf import PdfWriter  # <-- Changed here


def concatenate_pdfs(target_folder, output_filename):
    merger = PdfWriter()  # <-- Changed here
    pdf_found = False

    print(f"Scanning '{target_folder}' for PDF files...")

    for root, dirs, files in os.walk(target_folder):
        for file in files:
            if file.lower().endswith('.pdf'):
                full_path = os.path.join(root, file)
                print(f"Adding: {full_path}")

                merger.append(full_path)
                pdf_found = True

    if pdf_found:
        merger.write(output_filename)
        merger.close()
        print(f"\nSuccess! All PDFs have been combined into: {output_filename}")
    else:
        print("\nNo PDF files found in the specified folder or its subfolders.")


if __name__ == "__main__":
    TARGET_DIRECTORY = "/Users/hdon/Calibre-Library/Claire/"
    OUTPUT_PDF = "combined_output.pdf"

    concatenate_pdfs(TARGET_DIRECTORY, OUTPUT_PDF)