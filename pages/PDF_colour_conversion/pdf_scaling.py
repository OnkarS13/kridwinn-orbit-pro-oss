import os
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import List, Tuple
import time
from pathlib import Path


def parallel_pdf_scaling(input_pdf: str, output_pdf: str, 
                        scaling_percent: int,
                        dpi: int = 300,
                        max_workers: int = None,
                        batch_size: int = 50):
    """
    Scale a PDF by the specified percentage using a simpler approach
    
    Parameters:
    - input_pdf: Input PDF file path
    - output_pdf: Output PDF file path
    - scaling_percent: Scaling percentage (0-150)
    - dpi: Resolution for processing (300 recommended)
    - max_workers: Maximum number of threads (None for auto-detection)
    - batch_size: Number of pages to process in each batch for memory management
    """
    
    print(f"Starting PDF scaling: {input_pdf}")
    print(f"Scaling to: {scaling_percent}%")
    print(f"DPI: {dpi}")
    
    # Open the input PDF
    doc = fitz.open(input_pdf)
    total_pages = len(doc)
    
    print(f"Total pages to scale: {total_pages}")
    
    # Create new document for output
    new_doc = fitz.open()
    
    start_time = time.time()
    
    try:
        # Calculate scale factor
        scale_factor = scaling_percent / 100.0
        
        # Process each page directly
        for page_num in range(total_pages):
            print(f"  Scaling page {page_num + 1}/{total_pages}")
            
            # Get the original page
            page = doc[page_num]
            original_rect = page.rect
            
            # Calculate new dimensions
            new_width = original_rect.width * scale_factor
            new_height = original_rect.height * scale_factor
            
            # Create new page with scaled dimensions
            new_page = new_doc.new_page(width=new_width, height=new_height)
            
            # Create scaling matrix
            mat = fitz.Matrix(scale_factor, scale_factor)
            
            # Copy the page content with scaling
            new_page.show_pdf_page(fitz.Rect(0, 0, new_width, new_height), doc, page_num, clip=None)
            
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
    print(f"\nSaving scaled PDF: {output_pdf}")
    new_doc.save(output_pdf)
    new_doc.close()
    
    total_time = time.time() - start_time
    print(f"\nScaling completed!")
    print(f"Total time: {total_time:.1f} seconds")
    print(f"Average time per page: {total_time/total_pages:.2f} seconds")
    print(f"Pages processed: {total_pages}")
    print(f"Output saved to: {output_pdf}")


def process_folder_pdfs_scaling(input_folder: str, output_folder: str, 
                               scaling_percent: int,
                               dpi: int = 300,
                               max_workers: int = None,
                               batch_size: int = 50):
    """
    Scale all PDF files in a folder
    
    Parameters:
    - input_folder: Input folder containing PDF files
    - output_folder: Output folder to save scaled PDFs
    - scaling_percent: Scaling percentage (0-150)
    - dpi: Resolution for processing (300 recommended)
    - max_workers: Maximum number of threads (None for auto-detection)
    - batch_size: Number of pages to process in each batch for memory management
    """
    
    # Check if input folder exists
    if not os.path.exists(input_folder):
        raise FileNotFoundError(f"Input folder not found: {input_folder}")
    
    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"Created output folder: {output_folder}")
    
    # Find all PDF files in input folder
    pdf_files = [f for f in os.listdir(input_folder) 
                 if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        print(f"No PDF files found in folder: {input_folder}")
        return
    
    print(f"Found {len(pdf_files)} PDF files to scale:")
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"  {i}. {pdf_file}")
    
    total_start_time = time.time()
    successful_files = 0
    failed_files = []
    
    # Process each PDF file
    for i, pdf_file in enumerate(pdf_files, 1):
        input_pdf_path = os.path.join(input_folder, pdf_file)
        
        # Create output filename (add suffix to avoid overwriting)
        base_name = os.path.splitext(pdf_file)[0]
        output_pdf_name = f"{base_name}_scaled_{scaling_percent}percent.pdf"
        output_pdf_path = os.path.join(output_folder, output_pdf_name)
        
        print(f"\n{'='*50}")
        print(f"Scaling file {i}/{len(pdf_files)}: {pdf_file}")
        print(f"Output will be: {output_pdf_name}")
        print(f"{'='*50}")
        
        try:
            # Process single PDF
            parallel_pdf_scaling(
                input_pdf=input_pdf_path,
                output_pdf=output_pdf_path,
                scaling_percent=scaling_percent,
                dpi=dpi,
                max_workers=max_workers,
                batch_size=batch_size
            )
            successful_files += 1
            print(f"Successfully scaled: {pdf_file}")
            
        except Exception as e:
            print(f"Failed to scale {pdf_file}: {str(e)}")
            failed_files.append(pdf_file)
    
    # Print summary
    total_time = time.time() - total_start_time
    print(f"\n{'='*60}")
    print(f"FOLDER SCALING SUMMARY")
    print(f"{'='*60}")
    print(f"Total files found: {len(pdf_files)}")
    print(f"Successfully scaled: {successful_files}")
    print(f"Failed: {len(failed_files)}")
    print(f"Total processing time: {total_time:.1f} seconds")
    print(f"Output folder: {output_folder}")
    
    if failed_files:
        print(f"\nFailed files:")
        for failed_file in failed_files:
            print(f"  - {failed_file}")
    
    print(f"\nFolder scaling completed!")


def process_single_or_folder_scaling(input_path: str, output_path: str, 
                                   scaling_percent: int,
                                   dpi: int = 300,
                                   max_workers: int = None,
                                   batch_size: int = 50):
    """
    Smart function that detects if input is a file or folder and processes accordingly
    
    Parameters:
    - input_path: Input PDF file path OR folder path containing PDFs
    - output_path: Output PDF file path OR output folder path
    - scaling_percent: Scaling percentage (0-150)
    - dpi: Resolution for processing (300 recommended)
    - max_workers: Maximum number of threads (None for auto-detection)
    - batch_size: Number of pages to process in each batch for memory management
    """
    
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input path not found: {input_path}")
    
    if os.path.isfile(input_path):
        # Single file processing
        if not input_path.lower().endswith('.pdf'):
            raise ValueError(f"Input file must be a PDF: {input_path}")
        
        print("Detected: Single PDF file scaling")
        parallel_pdf_scaling(
            input_pdf=input_path,
            output_pdf=output_path,
            scaling_percent=scaling_percent,
            dpi=dpi,
            max_workers=max_workers,
            batch_size=batch_size
        )
        
    elif os.path.isdir(input_path):
        # Folder processing
        print("Detected: Folder scaling")
        process_folder_pdfs_scaling(
            input_folder=input_path,
            output_folder=output_path,
            scaling_percent=scaling_percent,
            dpi=dpi,
            max_workers=max_workers,
            batch_size=batch_size
        )
        
    else:
        raise ValueError(f"Invalid input path: {input_path}")


if __name__ == "__main__":
    # Example usage
    input_path = r"input_pdfs"
    output_path = r"scaled_output"
    
    process_single_or_folder_scaling(
        input_path=input_path,
        output_path=output_path,
        scaling_percent=75,  # Scale to 75% of original size
        dpi=300,
        max_workers=4,
        batch_size=25
    )
