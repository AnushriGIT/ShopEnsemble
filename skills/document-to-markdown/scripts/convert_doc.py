import os
import sys
import subprocess

def install_package(package_name):
    """Installs a python package using the current interpreter's pip."""
    print(f"Installing missing dependency: {package_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"Successfully installed {package_name}")
        return True
    except Exception as e:
        print(f"Failed to install {package_name}: {e}")
        return False

# Ensure dependencies are available
try:
    import pypdf
except ImportError:
    if not install_package("pypdf"):
        print("Error: pypdf is required to convert PDF files.")
        sys.exit(1)
    import pypdf

try:
    import docx
except ImportError:
    if not install_package("python-docx"):
        print("Error: python-docx is required to convert Word files.")
        sys.exit(1)
    import docx

def convert_pdf_to_md(input_path):
    """Extracts text page-by-page from PDF and formats it to Markdown."""
    print(f"Parsing PDF: {input_path}")
    md_content = []
    
    # Extract file base name for headers
    filename = os.path.basename(input_path)
    md_content.append(f"# PDF Document: {filename}\n")
    
    with open(input_path, 'rb') as f:
        reader = pypdf.PdfReader(f)
        num_pages = len(reader.pages)
        print(f"Found {num_pages} pages.")
        
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            md_content.append(f"## Page {i + 1} of {num_pages}\n")
            if text:
                md_content.append(text.strip())
            else:
                md_content.append("*[No text found on this page (possibly scanned image or empty)]*")
            md_content.append("\n\n---\n")
            
    return "\n".join(md_content)

def convert_docx_to_md(input_path):
    """Extracts paragraphs and headings from Word (.docx) file."""
    print(f"Parsing DOCX: {input_path}")
    md_content = []
    
    filename = os.path.basename(input_path)
    md_content.append(f"# Word Document: {filename}\n")
    
    doc = docx.Document(input_path)
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        
        # Simple mapping of style names to Markdown headings
        style_name = paragraph.style.name.lower()
        if 'heading 1' in style_name:
            md_content.append(f"# {text}\n")
        elif 'heading 2' in style_name:
            md_content.append(f"## {text}\n")
        elif 'heading 3' in style_name:
            md_content.append(f"### {text}\n")
        elif 'list' in style_name:
            md_content.append(f"* {text}")
        else:
            md_content.append(f"{text}\n")
            
    return "\n".join(md_content)

def convert_txt_to_md(input_path):
    """Wraps text/log file content in standard Markdown block representation."""
    print(f"Parsing Text/Log: {input_path}")
    md_content = []
    
    filename = os.path.basename(input_path)
    md_content.append(f"# Text File: {filename}\n")
    
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    md_content.append("```text")
    md_content.append(content)
    md_content.append("```")
    return "\n".join(md_content)

def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_doc.py <input_file_path> [output_file_path]")
        sys.exit(1)
        
    input_path = os.path.abspath(sys.argv[1])
    if not os.path.exists(input_path):
        print(f"Error: Input file '{input_path}' does not exist.")
        sys.exit(1)
        
    ext = os.path.splitext(input_path)[1].lower()
    
    if len(sys.argv) >= 3:
        output_path = os.path.abspath(sys.argv[2])
    else:
        # Default output path is <input_name>.md
        output_path = os.path.splitext(input_path)[0] + ".md"
        
    try:
        if ext == ".pdf":
            md_text = convert_pdf_to_md(input_path)
        elif ext == ".docx":
            md_text = convert_docx_to_md(input_path)
        elif ext in [".txt", ".log", ".rtf", ".ini", ".cfg", ".json"]:
            md_text = convert_txt_to_md(input_path)
        else:
            print(f"Unsupported format '{ext}'. Attempting raw text extraction...")
            md_text = convert_txt_to_md(input_path)
            
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_text)
            
        print(f"\nSuccess! Markdown file created at:\n{output_path}")
        
    except Exception as e:
        print(f"An error occurred during conversion: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
