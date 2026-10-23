"""
PDF Margin Adjustment Module

This module provides functionality to adjust margins (add or trim) for PDF files.
Supports both single PDF files and folders containing multiple PDFs.

Features:
- Add or trim margins on all sides (top, bottom, left, right)
- Values in millimeters (mm)
- Negative values = trim margins, Positive values = add margins
- Batch processing for folders
- Progress tracking
"""

import os
import fitz  # PyMuPDF
import time
from pathlib import Path
from typing import List, Tuple


def adjust_single_pdf_margins(input_pdf: str, output_pdf: str, 
                             top_margin: int, bottom_margin: int, 
                             left_margin: int, right_margin: int,
                             dpi: int = 300):
    """
    Adjust margins for a single PDF file
    
    Parameters:
    - input_pdf: Input PDF file path
    - output_pdf: Output PDF file path
    - top_margin: Top margin adjustment in mm (negative = trim, positive = add)
    - bottom_margin: Bottom margin adjustment in mm
    - left_margin: Left margin adjustment in mm
    - right_margin: Right margin adjustment in mm
    - dpi: Resolution for processing (300 recommended)
    """
    
    print(f"Starting PDF margin adjustment: {input_pdf}")
    print(f"Margins - Top: {top_margin}mm, Bottom: {bottom_margin}mm, Left: {left_margin}mm, Right: {right_margin}mm")
    print(f"DPI: {dpi}")
    
    # Open the input PDF
    doc = fitz.open(input_pdf)
    total_pages = len(doc)
    
    print(f"Total pages to adjust: {total_pages}")
    
    # Create new document for output
    new_doc = fitz.open()
    
    start_time = time.time()
    
    try:
        # Convert mm to points (1 mm = 2.834645669 points)
        mm_to_points = 2.834645669
        
        # Process each page
        for page_num in range(total_pages):
            print(f"  Adjusting page {page_num + 1}/{total_pages}")
            
            # Get the original page
            page = doc[page_num]
            original_rect = page.rect
            
            # Calculate new dimensions with margin adjustments
            top_adj = top_margin * mm_to_points
            bottom_adj = bottom_margin * mm_to_points
            left_adj = left_margin * mm_to_points
            right_adj = right_margin * mm_to_points
            
            # Calculate new page dimensions
            new_width = original_rect.width + left_adj + right_adj
            new_height = original_rect.height + top_adj + bottom_adj
            
            # Ensure minimum dimensions
            new_width = max(new_width, 72)  # Minimum 1 inch width
            new_height = max(new_height, 72)  # Minimum 1 inch height
            
            # Create new page with adjusted dimensions
            new_page = new_doc.new_page(width=new_width, height=new_height)
            
            # Calculate the source rectangle (what part of original page to copy)
            # For trimming: start from offset, for adding: start from 0
            src_x0 = max(0, -left_adj)  # Don't go negative
            src_y0 = max(0, -top_adj)   # Don't go negative
            src_x1 = min(original_rect.width, original_rect.width - right_adj)
            src_y1 = min(original_rect.height, original_rect.height - bottom_adj)
            
            # Calculate the destination rectangle (where to place the content)
            dest_x0 = max(0, left_adj)   # Start from left margin
            dest_y0 = max(0, top_adj)    # Start from top margin
            dest_x1 = dest_x0 + (src_x1 - src_x0)
            dest_y1 = dest_y0 + (src_y1 - src_y0)
            
            # Create rectangles
            src_rect = fitz.Rect(src_x0, src_y0, src_x1, src_y1)
            dest_rect = fitz.Rect(dest_x0, dest_y0, dest_x1, dest_y1)
            
            # Copy the page content with margin adjustment
            if src_rect.width > 0 and src_rect.height > 0 and dest_rect.width > 0 and dest_rect.height > 0:
                new_page.show_pdf_page(dest_rect, doc, page_num, clip=src_rect)
            
            if (page_num + 1) % 10 == 0 or page_num == total_pages - 1:
                elapsed_time = time.time() - start_time
                avg_time_per_page = elapsed_time / (page_num + 1)
                remaining_pages = total_pages - (page_num + 1)
                estimated_remaining_time = avg_time_per_page * remaining_pages
                
                print(f"  Progress: {page_num + 1}/{total_pages} pages")
                print(f"  Elapsed time: {elapsed_time:.1f}s, Est. remaining: {estimated_remaining_time:.1f}s")
    
    finally:
        # Always close the input document
        doc.close()
    
    # Save and close output document
    print(f"\nSaving margin-adjusted PDF: {output_pdf}")
    new_doc.save(output_pdf)
    new_doc.close()
    
    total_time = time.time() - start_time
    print(f"\nMargin adjustment completed!")
    print(f"Total time: {total_time:.1f} seconds")
    print(f"Average time per page: {total_time/total_pages:.2f} seconds")
    print(f"Pages processed: {total_pages}")
    print(f"Output saved to: {output_pdf}")


def process_folder_pdfs_margin_adjustment(input_folder: str, output_folder: str, 
                                        top_margin: int, bottom_margin: int, 
                                        left_margin: int, right_margin: int,
                                        dpi: int = 300,
                                        max_workers: int = None,
                                        batch_size: int = 50):
    """
    Process all PDF files in a folder with margin adjustment
    
    Parameters:
    - input_folder: Input folder path containing PDF files
    - output_folder: Output folder path for processed PDFs
    - top_margin: Top margin adjustment in mm
    - bottom_margin: Bottom margin adjustment in mm
    - left_margin: Left margin adjustment in mm
    - right_margin: Right margin adjustment in mm
    - dpi: Resolution for processing
    - max_workers: Maximum number of worker threads (unused in current implementation)
    - batch_size: Batch size for processing (unused in current implementation)
    """
    
    print(f"Starting folder margin adjustment: {input_folder}")
    print(f"Output folder: {output_folder}")
    
    # Find all PDF files
    input_path = Path(input_folder)
    pdf_files = list(input_path.glob("*.pdf"))
    
    if not pdf_files:
        print("No PDF files found in the input folder")
        return
    
    print(f"Found {len(pdf_files)} PDF files to process")
    
    # Create output directory
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)
    
    start_time = time.time()
    successful_files = 0
    failed_files = []
    
    # Process each PDF file
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"\n{'='*50}")
        print(f"Processing file {i}/{len(pdf_files)}: {pdf_file.name}")
        print(f"{'='*50}")
        
        try:
            # Generate output filename
            output_filename = f"{pdf_file.stem}_margins_adjusted.pdf"
            output_file = output_path / output_filename
            
            print(f"Output will be: {output_filename}")
            
            # Process the PDF
            adjust_single_pdf_margins(
                input_pdf=str(pdf_file),
                output_pdf=str(output_file),
                top_margin=top_margin,
                bottom_margin=bottom_margin,
                left_margin=left_margin,
                right_margin=right_margin,
                dpi=dpi
            )
            
            successful_files += 1
            print(f"✅ Successfully processed: {pdf_file.name}")
            
        except Exception as e:
            print(f"❌ Failed to process {pdf_file.name}: {str(e)}")
            failed_files.append(pdf_file.name)
    
    # Print summary
    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"FOLDER MARGIN ADJUSTMENT SUMMARY")
    print(f"{'='*60}")
    print(f"Total files found: {len(pdf_files)}")
    print(f"Successfully processed: {successful_files}")
    print(f"Failed: {len(failed_files)}")
    print(f"Total processing time: {total_time:.1f} seconds")
    print(f"Output folder: {output_folder}")
    
    if failed_files:
        print(f"\nFailed files:")
        for failed_file in failed_files:
            print(f"  - {failed_file}")
    
    print(f"\nFolder margin adjustment completed!")


def process_single_or_folder_margin_adjustment(input_path: str, output_path: str, 
                                             top_margin: int, bottom_margin: int, 
                                             left_margin: int, right_margin: int,
                                             dpi: int = 300,
                                             max_workers: int = None,
                                             batch_size: int = 50):
    """
    Process either a single PDF file or a folder of PDFs with margin adjustment
    
    Parameters:
    - input_path: Input PDF file path or folder path
    - output_path: Output PDF file path or folder path
    - top_margin: Top margin adjustment in mm
    - bottom_margin: Bottom margin adjustment in mm
    - left_margin: Left margin adjustment in mm
    - right_margin: Right margin adjustment in mm
    - dpi: Resolution for processing
    - max_workers: Maximum number of worker threads
    - batch_size: Batch size for processing
    """
    
    input_path_obj = Path(input_path)
    
    if input_path_obj.is_file() and input_path_obj.suffix.lower() == '.pdf':
        # Single PDF file
        print("Detected: Single PDF file")
        adjust_single_pdf_margins(
            input_pdf=input_path,
            output_pdf=output_path,
            top_margin=top_margin,
            bottom_margin=bottom_margin,
            left_margin=left_margin,
            right_margin=right_margin,
            dpi=dpi
        )
    elif input_path_obj.is_dir():
        # Folder of PDFs
        print("Detected: Folder")
        process_folder_pdfs_margin_adjustment(
            input_folder=input_path,
            output_folder=output_path,
            top_margin=top_margin,
            bottom_margin=bottom_margin,
            left_margin=left_margin,
            right_margin=right_margin,
            dpi=dpi,
            max_workers=max_workers,
            batch_size=batch_size
        )
    else:
        raise ValueError(f"Input path must be a PDF file or directory: {input_path}")


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 7:
        print("Usage: python pdf_margin_adjustment.py <input_path> <output_path> <top_margin> <bottom_margin> <left_margin> <right_margin> [dpi]")
        print("Example: python pdf_margin_adjustment.py input.pdf output.pdf 10 -5 0 0 300")
        print("Margins in mm: negative = trim, positive = add")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    top_margin = int(sys.argv[3])
    bottom_margin = int(sys.argv[4])
    left_margin = int(sys.argv[5])
    right_margin = int(sys.argv[6])
    dpi = int(sys.argv[7]) if len(sys.argv) > 7 else 300
    
    process_single_or_folder_margin_adjustment(
        input_path=input_path,
        output_path=output_path,
        top_margin=top_margin,
        bottom_margin=bottom_margin,
        left_margin=left_margin,
        right_margin=right_margin,
        dpi=dpi
    )
