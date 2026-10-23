# pdf_dpi_adjustment.py
import os
import fitz
from typing import Optional, List


def apply_dpi_to_pdf(input_path: str, output_path: str, x_dpi: int, y_dpi: int) -> bool:
    """
    Re-render PDF pages with specified DPI settings.
    This changes the resolution/quality of the PDF content.
    """
    doc = None
    out_doc = None
    
    try:
        doc = fitz.open(input_path)
        out_doc = fitz.open()  # New empty PDF
        
        # Calculate scale factors from 72 DPI base
        scale_x = max(1.0, float(x_dpi) / 72.0)
        scale_y = max(1.0, float(y_dpi) / 72.0)
        mat = fitz.Matrix(scale_x, scale_y)
        
        # Process each page
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # Render page at specified DPI
            pix = page.get_pixmap(matrix=mat)
            
            # Create new page with rendered content
            new_page = out_doc.new_page(
                width=page.rect.width,
                height=page.rect.height
            )
            new_page.insert_image(new_page.rect, pixmap=pix)
            
            # Clear memory
            pix = None
            page = None
        
        out_doc.save(output_path, garbage=4, deflate=True, clean=True)
        return True
        
    except Exception as e:
        print(f"DPI adjustment error: {e}")
        return False
        
    finally:
        if doc:
            doc.close()
        if out_doc:
            out_doc.close()


def process_single_or_folder_dpi(
    input_path: str,
    output_path: str,
    x_dpi: int,
    y_dpi: int,
    include_files: Optional[List[str]] = None
) -> str:
    """Process folder or single PDF with DPI adjustment"""
    os.makedirs(output_path, exist_ok=True)
    
    if os.path.isfile(input_path):
        # Single file
        output_file = os.path.join(output_path, os.path.basename(input_path))
        apply_dpi_to_pdf(input_path, output_file, x_dpi, y_dpi)
        return output_file
    
    # Folder mode
    pdfs = include_files if include_files else [
        os.path.join(input_path, f) 
        for f in os.listdir(input_path) 
        if f.lower().endswith('.pdf')
    ]
    
    last_output = output_path
    for pdf_path in pdfs:
        name = os.path.basename(pdf_path)
        out_file = os.path.join(output_path, name)
        if apply_dpi_to_pdf(pdf_path, out_file, x_dpi, y_dpi):
            last_output = out_file
    
    return last_output