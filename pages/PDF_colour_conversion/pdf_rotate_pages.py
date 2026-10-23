import os
import shutil
from typing import List, Optional


def rotate_pdf(in_path: str, out_path: str, angle: int) -> bool:
    """
    Rotate every page of a PDF by the specified angle.
    Hybrid approach: Fast for moderate PDFs, handles huge PDFs efficiently.
    Returns True on success, False on failure.
    """
    import fitz  # PyMuPDF
    
    # Validate angle
    if angle not in (0, 90, 180, 270):
        angle = 0
    
    # Skip processing if no rotation needed - direct file copy
    if angle == 0:
        try:
            shutil.copy2(in_path, out_path)
            return True
        except Exception as e:
            return False
    
    doc = None
    
    try:
        doc = fitz.open(in_path)
        
        # Rotate all pages - PyMuPDF handles memory efficiently
        for page in doc:
            page.set_rotation((page.rotation + angle) % 360)
        
        # Incremental save with compression for huge files
        doc.save(
            out_path,
            garbage=4,      # Clean up unused objects
            deflate=True,   # Compress for smaller file size
            clean=True      # Clean up content streams
        )
        return True
        
    except Exception as e:
        return False
        
    finally:
        if doc is not None:
            doc.close()


def rotate_folder(
    input_path: str, 
    output_path: str, 
    angle: int, 
    include_files: Optional[List[str]] = None
) -> List[str]:
    """
    Rotate all PDFs in a folder sequentially.
    
    Args:
        input_path: Folder containing input PDFs
        output_path: Folder to save rotated PDFs
        angle: Rotation angle (0, 90, 180, or 270 degrees)
        include_files: Optional list of specific file paths to process
        
    Returns:
        List of successfully processed output file paths
    """
    os.makedirs(output_path, exist_ok=True)
    
    # Get list of PDFs to process
    if include_files is None:
        pdfs = [
            os.path.join(input_path, f) 
            for f in sorted(os.listdir(input_path)) 
            if f.lower().endswith('.pdf')
        ]
    else:
        pdfs = include_files
    
    successful_outputs = []
    
    # Process one PDF at a time (sequential for huge files)
    for src in pdfs:
        name = os.path.basename(src)
        name_noext, _ = os.path.splitext(name)
        out = os.path.join(output_path, f"{name_noext}_rotated.pdf")
        
        if rotate_pdf(src, out, angle):
            successful_outputs.append(out)
    
    return successful_outputs