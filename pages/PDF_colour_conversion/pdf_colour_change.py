import fitz  # PyMuPDF
import numpy as np
import cv2
from PIL import Image
import io
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import Tuple, List, Dict, Any
import time
import os

def cmyk_to_rgb(c, m, y, k):
    """Convert CMYK (0-100) to RGB (0-255)"""
    c, m, y, k = c/100, m/100, y/100, k/100
    
    r = 255 * (1 - c) * (1 - k)
    g = 255 * (1 - m) * (1 - k)
    b = 255 * (1 - y) * (1 - k)
    
    return int(r), int(g), int(b)

def load_color_regions(json_file: str) -> Dict[str, Any]:
    try:
        with open(json_file, 'r') as f:
            config = json.load(f)
        
        if 'regions' not in config:
            raise ValueError("JSON must contain 'regions' key")
        
        # Convert CMYK values to RGB for each region
        for region in config['regions']:
            if 'cmyk' in region:
                region['rgb'] = cmyk_to_rgb(*region['cmyk'])
        
        # Add default settings if not present
        if 'settings' not in config:
            config['settings'] = {
                "x_dpi": 300,
                "y_dpi": 300,
                "max_workers": 4,
                "batch_size": 25
            }
        else:
            # Handle legacy dpi field and ensure x_dpi/y_dpi are present
            settings = config['settings']
            if 'dpi' in settings and 'x_dpi' not in settings:
                # Legacy format - convert single dpi to x_dpi and y_dpi
                settings['x_dpi'] = settings['y_dpi'] = settings['dpi']
                del settings['dpi']
            elif 'x_dpi' not in settings:
                settings['x_dpi'] = 300
            elif 'y_dpi' not in settings:
                settings['y_dpi'] = 300
        
        return config
        
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {json_file}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {e}")
    except Exception as e:
        raise ValueError(f"Error loading configuration: {e}")

def normalize_coordinates(coords: List[float], page_width: float, page_height: float) -> Tuple[int, int, int, int]:
    """
    Normalize coordinates based on page dimensions
    
    Args:
        coords: [x1, y1, x2, y2] coordinates (can be pixels or normalized 0-1)
        page_width: Page width in pixels
        page_height: Page height in pixels
        
    Returns:
        Tuple of normalized integer coordinates (x1, y1, x2, y2)
    """
    x1, y1, x2, y2 = coords
    
    # If coordinates are between 0-1, treat as normalized coordinates
    if all(0 <= coord <= 1 for coord in coords):
        x1 = int(x1 * page_width)
        y1 = int(y1 * page_height)
        x2 = int(x2 * page_width)
        y2 = int(y2 * page_height)
    else:
        # Treat as pixel coordinates
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
    
    # Ensure coordinates are within bounds
    x1 = max(0, min(x1, int(page_width)))
    y1 = max(0, min(y1, int(page_height)))
    x2 = max(0, min(x2, int(page_width)))
    y2 = max(0, min(y2, int(page_height)))
    
    # Ensure x1 < x2 and y1 < y2
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1
    
    return x1, y1, x2, y2

def apply_region_colors(binary_image: np.ndarray, original_image: np.ndarray, regions: List[Dict], 
                       page_width: float, page_height: float) -> np.ndarray:
    """
    Apply colors to specific rectangular regions while preserving original background
    """
    height, width = binary_image.shape
    # Use original image as background instead of white
    output = original_image.copy()
    
    # Rest of the function stays the same...
    
    # Create a priority mask to handle overlapping regions
    priority_mask = np.zeros((height, width), dtype=np.int32) - 1  # -1 means no region assigned
    
    # Sort regions by priority (if specified) or by area (smaller regions have higher priority)
    sorted_regions = sorted(regions, key=lambda r: r.get('priority', 
                           (r['coordinates'][2] - r['coordinates'][0]) * 
                           (r['coordinates'][3] - r['coordinates'][1])))
    
    for idx, region in enumerate(sorted_regions):
        # Get normalized coordinates
        x1, y1, x2, y2 = normalize_coordinates(region['coordinates'], page_width, page_height)
        
        # Skip invalid regions
        if x1 >= x2 or y1 >= y2:
            print(f"  Warning: Invalid region coordinates: {region['coordinates']}")
            continue
        
        # Ensure coordinates are within image bounds
        x1 = max(0, min(x1, width))
        y1 = max(0, min(y1, height))
        x2 = max(0, min(x2, width))
        y2 = max(0, min(y2, height))
        
        if x1 >= x2 or y1 >= y2:
            continue
        
        # Extract region from binary image
        region_binary = binary_image[y1:y2, x1:x2]

        text_intensity = region_binary.astype(np.float32) / 255.0
        text_pixels = text_intensity > 0.1  # Any pixel with some text content
        
        if np.any(text_pixels):
            # Get RGB color (BGR format for OpenCV)
            rgb_color = region['rgb']
            bgr_color = [rgb_color[2], rgb_color[1], rgb_color[0]]
            
            # Apply color to text pixels in this region
            region_output = output[y1:y2, x1:x2]
            region_priority = priority_mask[y1:y2, x1:x2]
            
            # Only apply color where this region has priority (higher index = higher priority)
            valid_pixels = text_pixels & (region_priority < idx)
            region_output[valid_pixels] = bgr_color
            region_priority[valid_pixels] = idx
            
            print(f"    Applied color {region['cmyk']} to region {region.get('name', f'Region_{idx}')}: "
                  f"({x1},{y1}) to ({x2},{y2}) - {np.sum(valid_pixels)} pixels")
    
    return output

def process_single_page_multiregion(page_data: dict) -> Tuple[int, bytes, Tuple[float, float]]:
    """
    Process a single page with multiple color regions
    
    Args:
        page_data: Dictionary containing page info and processing parameters
        
    Returns:
        Tuple of (page_number, processed_image_bytes, page_dimensions)
    """
    page_num = page_data['page_num']
    page_bytes = page_data['page_bytes']
    page_rect = page_data['page_rect']
    regions = page_data['regions']
    x_dpi = page_data['x_dpi']
    y_dpi = page_data['y_dpi']
    
    try:
        print(f"  Processing page {page_num + 1} with {len(regions)} regions in thread {threading.current_thread().name}")
        
        # Create pixmap from bytes
        pix = fitz.Pixmap(page_bytes)
        
        # Convert to numpy array
        img_data = pix.tobytes("png")
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        
        # Convert to grayscale for thresholding
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Use a lower threshold to catch more pixels
        _, binary = cv2.threshold(gray, 70, 255, cv2.THRESH_BINARY)  # Even lower
        binary = cv2.bitwise_not(binary)  # Invert so text pixels are white

        # Apply morphological operations to fill gaps and smooth edges
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)  # Fill small gaps
        binary = cv2.dilate(binary, kernel, iterations=1)  # Expand text regions slightly
        
        # Apply colors to specified regions
        output = apply_region_colors(binary, img, regions, img.shape[1], img.shape[0])
        
        # Convert output to RGB for PIL
        output_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
        
        # Convert to PIL Image
        pil_img = Image.fromarray(output_rgb)
        
        # Convert to bytes
        img_bytes = io.BytesIO()
        pil_img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        # Clean up
        pix = None
        
        print(f"    Page {page_num + 1} processing completed")
        return page_num, img_bytes.getvalue(), (page_rect.width, page_rect.height)
        
    except Exception as e:
        print(f"    Error processing page {page_num + 1}: {str(e)}")
        raise

def parallel_pdf_multiregion_color_change(input_pdf: str, output_pdf: str, 
                                         config_json: str,
                                         x_dpi: int = 300,
                                         y_dpi: int = 300,
                                         max_workers: int = None,
                                         batch_size: int = 50):
    """
    Parallel PDF color changing with multiple rectangular regions
    
    Parameters:
    - input_pdf: Input PDF file path
    - output_pdf: Output PDF file path
    - config_json: JSON configuration file with region definitions
    - x_dpi: X-axis resolution for processing (300 recommended)
    - y_dpi: Y-axis resolution for processing (300 recommended)
    - max_workers: Maximum number of threads (None for auto-detection)
    - batch_size: Number of pages to process in each batch for memory management
    """
    
    print(f"Starting parallel multi-region processing of PDF: {input_pdf}")
    print(f"Configuration file: {config_json}")
    print(f"DPI: X={x_dpi}, Y={y_dpi}")
    
    # Load configuration
    config = load_color_regions(config_json)
    regions = config['regions']
    
    print(f"Loaded {len(regions)} color regions:")
    for i, region in enumerate(regions):
        print(f"  {i+1}. {region.get('name', f'Region_{i}')}: CMYK{region['cmyk']} -> RGB{region['rgb']} at {region['coordinates']}")
    
    # Auto-detect optimal number of workers if not specified
    if max_workers is None:
        max_workers = min(32, (os.cpu_count() or 1) + 4)
    
    print(f"Using {max_workers} worker threads")
    print(f"Batch size: {batch_size} pages")
    
    # Open the input PDF
    doc = fitz.open(input_pdf)
    total_pages = len(doc)
    
    print(f"Total pages to process: {total_pages}")
    
    # Create new document for output
    new_doc = fitz.open()
    
    start_time = time.time()
    
    try:
        # Process pages in batches to manage memory
        for batch_start in range(0, total_pages, batch_size):
            batch_end = min(batch_start + batch_size, total_pages)
            batch_pages = batch_end - batch_start
            
            print(f"\nProcessing batch: pages {batch_start + 1} to {batch_end} ({batch_pages} pages)")
            
            # Prepare page data for current batch
            page_data_list = []
            for page_num in range(batch_start, batch_end):
                page = doc[page_num]
                
                # Convert page to pixmap and get bytes
                mat = fitz.Matrix(x_dpi/72, y_dpi/72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                page_bytes = pix.tobytes("png")
                
                page_data = {
                    'page_num': page_num,
                    'page_bytes': page_bytes,
                    'page_rect': page.rect,
                    'regions': regions,
                    'x_dpi': x_dpi,
                    'y_dpi': y_dpi
                }
                page_data_list.append(page_data)
                
                # Clean up pixmap immediately
                pix = None
            
            # Process batch in parallel
            processed_pages = {}
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all pages in current batch
                future_to_page = {
                    executor.submit(process_single_page_multiregion, page_data): page_data['page_num']
                    for page_data in page_data_list
                }
                
                # Collect results as they complete
                completed_count = 0
                for future in as_completed(future_to_page):
                    page_num = future_to_page[future]
                    try:
                        page_result = future.result()
                        processed_pages[page_result[0]] = page_result
                        completed_count += 1
                        
                        if completed_count % 10 == 0 or completed_count == batch_pages:
                            print(f"    Completed {completed_count}/{batch_pages} pages in current batch")
                            
                    except Exception as e:
                        print(f"    Page {page_num + 1} failed: {str(e)}")
                        raise
            
            # Add processed pages to output document in correct order
            print(f"  Adding batch pages to output document...")
            for page_num in range(batch_start, batch_end):
                if page_num in processed_pages:
                    _, img_bytes, (width, height) = processed_pages[page_num]
                    
                    # Create pixmap from processed image
                    img_pixmap = fitz.Pixmap(img_bytes)
                    
                    # Create new page with original dimensions
                    new_page = new_doc.new_page(width=width, height=height)
                    
                    # Insert image to fill the page
                    page_rect = fitz.Rect(0, 0, width, height)
                    new_page.insert_image(page_rect, pixmap=img_pixmap)
                    
                    # Clean up
                    img_pixmap = None
                else:
                    print(f"    Warning: Page {page_num + 1} not found in processed results")
            
            # Clear processed pages to free memory
            processed_pages.clear()
            page_data_list.clear()
            
            elapsed_time = time.time() - start_time
            pages_processed = batch_end
            avg_time_per_page = elapsed_time / pages_processed
            remaining_pages = total_pages - pages_processed
            estimated_remaining_time = avg_time_per_page * remaining_pages
            
            print(f"  Batch completed. Progress: {pages_processed}/{total_pages} pages")
            print(f"  Elapsed time: {elapsed_time:.1f}s, Est. remaining: {estimated_remaining_time:.1f}s")
    
    finally:
        # Always close the input document
        doc.close()
    
    # Save and close output document
    print(f"\nSaving output PDF: {output_pdf}")
    new_doc.save(output_pdf)
    new_doc.close()
    
    total_time = time.time() - start_time
    print(f"\nProcessing completed!")
    print(f"Total time: {total_time:.1f} seconds")
    print(f"Average time per page: {total_time/total_pages:.2f} seconds")
    print(f"Pages processed: {total_pages}")
    print(f"Output saved to: {output_pdf}")

def process_folder_pdfs(input_folder: str, output_folder: str, 
                       config_json: str,
                       x_dpi: int = 300,
                       y_dpi: int = 300,
                       max_workers: int = None,
                       batch_size: int = 50):
    """
    Process all PDF files in a folder with multi-region color changing
    
    Parameters:
    - input_folder: Input folder containing PDF files
    - output_folder: Output folder to save processed PDFs
    - config_json: JSON configuration file with region definitions
    - x_dpi: X-axis resolution for processing (300 recommended)
    - y_dpi: Y-axis resolution for processing (300 recommended)
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
    
    print(f"Found {len(pdf_files)} PDF files to process:")
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
        output_pdf_name = f"{base_name}_colored.pdf"
        output_pdf_path = os.path.join(output_folder, output_pdf_name)
        
        print(f"\n{'='*50}")
        print(f"Processing file {i}/{len(pdf_files)}: {pdf_file}")
        print(f"Output will be: {output_pdf_name}")
        print(f"{'='*50}")
        
        try:
            # Process single PDF
            parallel_pdf_multiregion_color_change(
                input_pdf=input_pdf_path,
                output_pdf=output_pdf_path,
                config_json=config_json,
                x_dpi=x_dpi,
                y_dpi=y_dpi,
                max_workers=max_workers,
                batch_size=batch_size
            )
            successful_files += 1
            print(f"Successfully processed: {pdf_file}")
            
        except Exception as e:
            print(f"Failed to process {pdf_file}: {str(e)}")
            failed_files.append(pdf_file)
    
    # Print summary
    total_time = time.time() - total_start_time
    print(f"\n{'='*60}")
    print(f"FOLDER PROCESSING SUMMARY")
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
    
    print(f"\nFolder processing completed!")

def process_single_or_folder(input_path: str, output_path: str, 
                            config_json: str,
                            x_dpi: int = 300,
                            y_dpi: int = 300,
                            max_workers: int = None,
                            batch_size: int = 50):
    """
    Smart function that detects if input is a file or folder and processes accordingly
    
    Parameters:
    - input_path: Input PDF file path OR folder path containing PDFs
    - output_path: Output PDF file path OR output folder path
    - config_json: JSON configuration file with region definitions
    - x_dpi: X-axis resolution for processing (300 recommended)
    - y_dpi: Y-axis resolution for processing (300 recommended)
    - max_workers: Maximum number of threads (None for auto-detection)
    - batch_size: Number of pages to process in each batch for memory management
    """
    
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input path not found: {input_path}")
    
    if os.path.isfile(input_path):
        # Single file processing
        if not input_path.lower().endswith('.pdf'):
            raise ValueError(f"Input file must be a PDF: {input_path}")
        
        print("Detected: Single PDF file processing")
        parallel_pdf_multiregion_color_change(
            input_pdf=input_path,
            output_pdf=output_path,
            config_json=config_json,
            x_dpi=x_dpi,
            y_dpi=y_dpi,
            max_workers=max_workers,
            batch_size=batch_size
        )
        
    elif os.path.isdir(input_path):
        # Folder processing
        print("Detected: Folder processing")
        process_folder_pdfs(
            input_folder=input_path,
            output_folder=output_path,
            config_json=config_json,
            x_dpi=x_dpi,
            y_dpi=y_dpi,
            max_workers=max_workers,
            batch_size=batch_size
        )
        
    else:
        raise ValueError(f"Invalid input path: {input_path}")

if __name__ == "__main__":
    config_json = r"config\config.json"

    # Load configuration 
    config = load_color_regions(config_json)
    settings = config['settings']

    # Get current script directory for default output
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_output = os.path.join(script_dir, "colored_output")
    
    # Example usage with multi-region processing
    process_single_or_folder(
        input_path=settings.get('input_path', r"input_pdfs"),
        output_path=default_output,
        config_json=config_json,
        dpi=settings.get('dpi', 300),
        max_workers=settings.get('max_workers', 4),
        batch_size=settings.get('batch_size', 25)
    )
    
    # You can also create custom configurations:
    custom_config = {
        "regions": [
            {
                "name": "Title Area",
                "coordinates": [100, 50, 500, 150],  # Pixel coordinates
                "cmyk": [100, 0, 100, 0],  # Green
                "priority": 1
            },
            {
                "name": "Main Content",
                "coordinates": [0.1, 0.2, 0.9, 0.8],  # Normalized coordinates
                "cmyk": [0, 50, 100, 0],  # Orange
                "priority": 2
            }
        ]
    }
    
    # Save custom configuration
    # with open("custom_config.json", 'w') as f:
    #     json.dump(custom_config, f, indent=2)
    
    # Use custom configuration
    # parallel_pdf_multiregion_color_change(
    #     input_pdf="input.pdf",
    #     output_pdf="output_custom.pdf", 
    #     config_json="custom_config.json",
    #     dpi=300
    # )